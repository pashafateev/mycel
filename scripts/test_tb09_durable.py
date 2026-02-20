from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from temporalio.client import Client

from tb09 import DEFAULT_DELIVERY_DB_PATH, DEFAULT_TASK_QUEUE
from tb09.scheduler import schedule_followups


async def wait_for_temporal(address: str, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            await Client.connect(address)
            return
        except Exception:
            await asyncio.sleep(1)
    raise RuntimeError(f"Temporal not ready on {address} after {timeout_seconds}s")


def kill_process_on_port(port: int) -> None:
    pids: list[str] = []
    try:
        output = subprocess.check_output(["lsof", "-ti", f"tcp:{port}"], text=True).strip()
        pids = [pid for pid in output.splitlines() if pid.strip()]
    except subprocess.CalledProcessError:
        pids = []
    except FileNotFoundError:
        pids = []

    if not pids:
        # Fallback when lsof isn't available.
        try:
            output = subprocess.check_output(
                ["pgrep", "-f", f"temporal server start-dev.*--port {port}"],
                text=True,
            ).strip()
            pids = [pid for pid in output.splitlines() if pid.strip()]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pids = []

    for pid in pids:
        os.kill(int(pid), signal.SIGTERM)

    # Best effort hard kill if still alive.
    if not pids:
        return

    time.sleep(1)
    for pid in pids:
        try:
            os.kill(int(pid), 0)
        except OSError:
            continue
        os.kill(int(pid), signal.SIGKILL)


def start_temporal_server(db_path: str, port: int) -> subprocess.Popen[Any]:
    cmd = [
        "temporal",
        "server",
        "start-dev",
        "--db-filename",
        db_path,
        "--port",
        str(port),
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def start_worker(address: str, task_queue: str, delivery_db_path: str) -> subprocess.Popen[Any]:
    env = dict(os.environ)
    env["TB09_DELIVERY_DB_PATH"] = delivery_db_path
    cmd = [
        sys.executable,
        "-m",
        "tb09.worker",
        "--address",
        address,
        "--task-queue",
        task_queue,
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, env=env)


def stop_process(proc: Optional[subprocess.Popen[Any]]) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def fetch_deliveries(db_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT reminder_id, message, chat_id, scheduled_at, expected_at, delivered_at
            FROM deliveries
            ORDER BY reminder_id
            """
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "reminder_id": row[0],
            "message": row[1],
            "chat_id": int(row[2]),
            "scheduled_at": float(row[3]),
            "expected_at": float(row[4]),
            "delivered_at": float(row[5]),
        }
        for row in rows
    ]


def fetch_attempt_counts(db_path: str) -> Dict[str, int]:
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT reminder_id, COUNT(*) FROM delivery_attempts GROUP BY reminder_id"
        ).fetchall()
    finally:
        conn.close()
    return {str(reminder_id): int(count) for reminder_id, count in rows}


async def run_test(address: str, port: int, temporal_db: str, delivery_db: str, task_queue: str) -> None:
    kill_process_on_port(port)
    Path(temporal_db).unlink(missing_ok=True)
    Path(delivery_db).unlink(missing_ok=True)

    server_proc = None
    worker_proc = None

    started_at = time.time()
    try:
        server_proc = start_temporal_server(temporal_db, port)
        await wait_for_temporal(address, timeout_seconds=40)

        worker_proc = start_worker(address, task_queue, delivery_db)
        await asyncio.sleep(3)

        client = await Client.connect(address)
        scheduled = await schedule_followups(
            client,
            task_queue=task_queue,
            db_path=delivery_db,
            delays=[30, 60, 90],
        )
        print("scheduled")
        for item in scheduled:
            print(
                f"workflow_id={item['workflow_id']} reminder_id={item['reminder_id']} "
                f"scheduled_at={item['scheduled_at']:.3f} expected_at={item['expected_at']:.3f}"
            )

        await asyncio.sleep(15)

        print("restarting temporal server")
        stop_process(worker_proc)
        worker_proc = None
        stop_process(server_proc)
        server_proc = None

        server_proc = start_temporal_server(temporal_db, port)
        await wait_for_temporal(address, timeout_seconds=40)

        worker_proc = start_worker(address, task_queue, delivery_db)

        timeout_seconds = 180
        deadline = started_at + timeout_seconds
        deliveries = []
        while time.time() < deadline:
            deliveries = fetch_deliveries(delivery_db)
            if len(deliveries) >= 3:
                break
            await asyncio.sleep(2)

        if len(deliveries) != 3:
            raise AssertionError(f"Expected 3 deliveries, found {len(deliveries)}")

        attempts = fetch_attempt_counts(delivery_db)
        by_id = {item["reminder_id"]: item for item in scheduled}

        print("timeline")
        for delivery in sorted(deliveries, key=lambda d: d["expected_at"]):
            reminder_id = delivery["reminder_id"]
            if reminder_id not in by_id:
                raise AssertionError(f"Unknown reminder delivered: {reminder_id}")
            delta = delivery["delivered_at"] - delivery["expected_at"]
            print(
                f"reminder_id={reminder_id} scheduled_at={delivery['scheduled_at']:.3f} "
                f"expected_at={delivery['expected_at']:.3f} delivered_at={delivery['delivered_at']:.3f} "
                f"delta={delta:.3f}s attempts={attempts.get(reminder_id, 0)}"
            )
            if abs(delta) > 10:
                raise AssertionError(
                    f"Delivery timing out of tolerance for {reminder_id}: delta={delta:.3f}s"
                )

        if len(set(item["reminder_id"] for item in deliveries)) != 3:
            raise AssertionError("Duplicate delivery rows detected")

        print("TB9 durable restart test passed")
    finally:
        stop_process(worker_proc)
        stop_process(server_proc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TB9 durable restart test")
    parser.add_argument("--address", default="localhost:7233")
    parser.add_argument("--port", type=int, default=7233)
    parser.add_argument("--temporal-db", default="/tmp/tb09_temporal.db")
    parser.add_argument("--delivery-db", default=DEFAULT_DELIVERY_DB_PATH)
    parser.add_argument("--task-queue", default=DEFAULT_TASK_QUEUE)
    args = parser.parse_args()

    asyncio.run(
        run_test(
            address=args.address,
            port=args.port,
            temporal_db=args.temporal_db,
            delivery_db=args.delivery_db,
            task_queue=args.task_queue,
        )
    )


if __name__ == "__main__":
    main()
