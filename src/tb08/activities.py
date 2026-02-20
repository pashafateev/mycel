from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from temporalio import activity
from temporalio.exceptions import ApplicationError

from .safe_exec import ExecPolicy, ExecStatus, run_safe_exec

ATTEMPT_COUNTER: dict[str, int] = {}


@activity.defn
async def exec_command_activity(payload: dict[str, Any]) -> dict[str, Any]:
    command = payload["command"]
    workspace_dir = Path(payload.get("workspace_dir") or ".").resolve()
    timeout_seconds: Optional[int] = payload.get("timeout_seconds")
    invocation_id = payload.get("invocation_id", command)

    ATTEMPT_COUNTER[invocation_id] = ATTEMPT_COUNTER.get(invocation_id, 0) + 1
    attempt = ATTEMPT_COUNTER[invocation_id]

    policy = ExecPolicy(workspace_dir=workspace_dir)
    result = await run_safe_exec(
        command=command,
        policy=policy,
        timeout_seconds=timeout_seconds,
        attempt=attempt,
    )

    if payload.get("raise_on_failure") and result.status != ExecStatus.SUCCESS:
        non_retryable = result.status == ExecStatus.BLOCKED
        raise ApplicationError(
            result.reason,
            asdict(result),
            type=result.status.value,
            non_retryable=non_retryable,
        )

    return asdict(result)
