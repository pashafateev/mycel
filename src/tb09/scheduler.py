from __future__ import annotations

import time
import uuid
from typing import Any, List, Optional

from temporalio.client import Client

from tb09 import DEFAULT_DELIVERY_DB_PATH, DEFAULT_TASK_QUEUE
from tb09.workflows import FollowUpWorkflow


async def schedule_followups(
    client: Client,
    task_queue: str = DEFAULT_TASK_QUEUE,
    db_path: str = DEFAULT_DELIVERY_DB_PATH,
    delays: Optional[List[int]] = None,
) -> List[dict[str, Any]]:
    delay_values = delays or [30, 60, 90]
    now_epoch = time.time()
    scheduled: List[dict[str, Any]] = []

    for delay in delay_values:
        reminder_id = f"tb09-{delay}s-{uuid.uuid4().hex[:8]}"
        workflow_id = f"tb09-followup-{reminder_id}"
        payload = {
            "id": reminder_id,
            "message": f"TB9 reminder after {delay}s",
            "deliver_after_seconds": delay,
            "chat_id": 4242,
            "db_path": db_path,
        }
        await client.start_workflow(
            FollowUpWorkflow.run,
            payload,
            id=workflow_id,
            task_queue=task_queue,
        )
        scheduled.append(
            {
                "workflow_id": workflow_id,
                "reminder_id": reminder_id,
                "delay_seconds": delay,
                "scheduled_at": now_epoch,
                "expected_at": now_epoch + delay,
            }
        )
    return scheduled
