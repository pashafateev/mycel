from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from tb09.workflows import FollowUpWorkflow, deliver_reminder


@pytest.mark.asyncio
async def test_tb09_single_followup_delivered_once(tmp_path: Path) -> None:
    db_path = str(tmp_path / "tb09-single.db")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="tb09-test-queue-single",
            workflows=[FollowUpWorkflow],
            activities=[deliver_reminder],
        ):
            handle = await env.client.start_workflow(
                FollowUpWorkflow.run,
                {
                    "id": "tb09-single",
                    "message": "single",
                    "deliver_after_seconds": 60,
                    "chat_id": 1,
                    "db_path": db_path,
                },
                id="tb09-single-workflow",
                task_queue="tb09-test-queue-single",
            )

            result = await handle.result()
            assert result["state"] == "DELIVERED"

    conn = sqlite3.connect(db_path)
    try:
        delivered_count = conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
        attempts = conn.execute(
            "SELECT COUNT(*) FROM delivery_attempts WHERE reminder_id = ?",
            ("tb09-single",),
        ).fetchone()[0]
    finally:
        conn.close()

    assert delivered_count == 1
    assert attempts == 1


@pytest.mark.asyncio
async def test_tb09_two_followups_no_duplicates(tmp_path: Path) -> None:
    db_path = str(tmp_path / "tb09-double.db")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="tb09-test-queue-double",
            workflows=[FollowUpWorkflow],
            activities=[deliver_reminder],
        ):
            handle1 = await env.client.start_workflow(
                FollowUpWorkflow.run,
                {
                    "id": "tb09-a",
                    "message": "a",
                    "deliver_after_seconds": 30,
                    "chat_id": 2,
                    "db_path": db_path,
                },
                id="tb09-workflow-a",
                task_queue="tb09-test-queue-double",
            )
            handle2 = await env.client.start_workflow(
                FollowUpWorkflow.run,
                {
                    "id": "tb09-b",
                    "message": "b",
                    "deliver_after_seconds": 60,
                    "chat_id": 2,
                    "db_path": db_path,
                },
                id="tb09-workflow-b",
                task_queue="tb09-test-queue-double",
            )

            result1 = await handle1.result()
            result2 = await handle2.result()
            assert result1["state"] == "DELIVERED"
            assert result2["state"] == "DELIVERED"

    conn = sqlite3.connect(db_path)
    try:
        deliveries = conn.execute(
            "SELECT reminder_id, COUNT(*) FROM deliveries GROUP BY reminder_id ORDER BY reminder_id"
        ).fetchall()
        attempts = conn.execute(
            "SELECT reminder_id, COUNT(*) FROM delivery_attempts GROUP BY reminder_id ORDER BY reminder_id"
        ).fetchall()
    finally:
        conn.close()

    assert deliveries == [("tb09-a", 1), ("tb09-b", 1)]
    assert attempts == [("tb09-a", 1), ("tb09-b", 1)]
