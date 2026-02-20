from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import exec_command_activity


@workflow.defn
class ExecWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            exec_command_activity,
            payload,
            schedule_to_close_timeout=timedelta(seconds=payload.get("activity_timeout", 45)),
            retry_policy=RetryPolicy(maximum_attempts=payload.get("max_attempts", 3)),
        )
