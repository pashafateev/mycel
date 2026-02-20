from __future__ import annotations

import os
import sqlite3
import time
from datetime import timedelta
from typing import Any, Optional

from temporalio import activity, workflow

from tb09 import DEFAULT_DELIVERY_DB_PATH


@activity.defn
async def deliver_reminder(payload: dict[str, Any]) -> dict[str, Any]:
    db_path = str(payload.get("db_path") or os.getenv("TB09_DELIVERY_DB_PATH") or DEFAULT_DELIVERY_DB_PATH)
    reminder_id = str(payload["id"])
    now_epoch = time.time()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reminder_id TEXT NOT NULL,
                attempted_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deliveries (
                reminder_id TEXT PRIMARY KEY,
                message TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                scheduled_at REAL NOT NULL,
                expected_at REAL NOT NULL,
                delivered_at REAL NOT NULL,
                workflow_id TEXT NOT NULL,
                run_id TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO delivery_attempts(reminder_id, attempted_at) VALUES (?, ?)",
            (reminder_id, now_epoch),
        )
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO deliveries(
                reminder_id, message, chat_id, scheduled_at, expected_at, delivered_at, workflow_id, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reminder_id,
                str(payload["message"]),
                int(payload["chat_id"]),
                float(payload["scheduled_at"]),
                float(payload["expected_at"]),
                now_epoch,
                str(payload["workflow_id"]),
                str(payload["run_id"]),
            ),
        )
        conn.commit()

        attempt_count = conn.execute(
            "SELECT COUNT(*) FROM delivery_attempts WHERE reminder_id = ?",
            (reminder_id,),
        ).fetchone()[0]
        delivered_row = conn.execute(
            "SELECT delivered_at FROM deliveries WHERE reminder_id = ?",
            (reminder_id,),
        ).fetchone()

        return {
            "reminder_id": reminder_id,
            "inserted": cursor.rowcount == 1,
            "attempt_count": int(attempt_count),
            "delivered_at": float(delivered_row[0]),
        }
    finally:
        conn.close()


@workflow.defn
class FollowUpWorkflow:
    def __init__(self) -> None:
        self._state = "INIT"
        self._reminder: Optional[dict[str, Any]] = None
        self._scheduled_at = 0.0
        self._expected_at = 0.0
        self._delivery_result: Optional[dict[str, Any]] = None

    @workflow.run
    async def run(self, reminder: dict[str, Any]) -> dict[str, Any]:
        delay = max(0, int(reminder["deliver_after_seconds"]))
        now = workflow.now()

        self._reminder = {
            "id": str(reminder["id"]),
            "message": str(reminder["message"]),
            "chat_id": int(reminder["chat_id"]),
            "deliver_after_seconds": delay,
            "db_path": str(reminder.get("db_path") or ""),
        }
        self._scheduled_at = now.timestamp()
        self._expected_at = (now + timedelta(seconds=delay)).timestamp()
        self._state = "PENDING"

        await workflow.sleep(timedelta(seconds=delay))
        self._state = "DELIVERING"

        info = workflow.info()
        self._delivery_result = await workflow.execute_activity(
            deliver_reminder,
            {
                "id": self._reminder["id"],
                "message": self._reminder["message"],
                "chat_id": self._reminder["chat_id"],
                "scheduled_at": self._scheduled_at,
                "expected_at": self._expected_at,
                "workflow_id": info.workflow_id,
                "run_id": info.run_id,
                "db_path": self._reminder.get("db_path") or "",
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        self._state = "DELIVERED"

        return self.get_status()

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        reminder_id = None
        if self._reminder is not None:
            reminder_id = self._reminder["id"]
        return {
            "state": self._state,
            "reminder_id": reminder_id,
            "scheduled_at": self._scheduled_at,
            "expected_at": self._expected_at,
            "delivery": self._delivery_result,
        }
