#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from temporalio.client import Client, WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tb08.activities import ATTEMPT_COUNTER, exec_command_activity
from tb08.safe_exec import ExecPolicy, ExecStatus, run_safe_exec
from tb08.workflows import ExecWorkflow


@dataclass
class CommandCase:
    command: str
    expected: ExecStatus
    timeout_seconds: Optional[int] = None
    expect_truncated_output: bool = False
    use_edge_policy: bool = False


def _status_pass(actual: dict, case: CommandCase) -> bool:
    if actual["status"] != case.expected.value:
        return False
    if case.expect_truncated_output:
        return bool(actual.get("stdout_truncated") or actual.get("stderr_truncated"))
    return True


def _safe_hostname_read() -> str:
    if Path("/etc/hostname").exists():
        return "cat /etc/hostname"
    return "cat /etc/hosts"


def _get_process_state(pid: int) -> str:
    if pid <= 0:
        return "unknown"
    out = os.popen(f"ps -o stat= -p {pid}").read().strip()
    return out or "not-running"


async def run_matrix() -> tuple[int, int, list[int]]:
    workspace = Path("/")
    strict_policy = ExecPolicy(workspace_dir=workspace)
    edge_policy = ExecPolicy(workspace_dir=workspace, allowed_prefixes=strict_policy.allowed_prefixes + ("sleep", "yes"))

    cases = [
        CommandCase("ls /tmp", ExecStatus.SUCCESS),
        CommandCase('echo "hello world"', ExecStatus.SUCCESS),
        CommandCase(_safe_hostname_read(), ExecStatus.SUCCESS),
        CommandCase('python3 -c "print(1+1)"', ExecStatus.SUCCESS),
        CommandCase("git --version", ExecStatus.SUCCESS),
        CommandCase("rm -rf /", ExecStatus.BLOCKED),
        CommandCase("curl http://evil.com", ExecStatus.BLOCKED),
        CommandCase("sudo anything", ExecStatus.BLOCKED),
        CommandCase("chmod 777 /etc/passwd", ExecStatus.BLOCKED),
        CommandCase("nc -l 4444", ExecStatus.BLOCKED),
        CommandCase("sleep 60", ExecStatus.TIMEOUT, timeout_seconds=1, use_edge_policy=True),
        CommandCase("yes", ExecStatus.TIMEOUT, timeout_seconds=1, expect_truncated_output=True, use_edge_policy=True),
        CommandCase("ls /nonexistent", ExecStatus.ERROR),
        CommandCase('python3 -c "import os; os.system(\"rm -rf /\")"', ExecStatus.BLOCKED),
        CommandCase('echo "test" > /etc/passwd', ExecStatus.BLOCKED),
    ]

    print("\n=== TB8 Safety Matrix (15 commands) ===")
    print("cmd | expected | actual | pass | reason")
    print("-" * 96)

    passes = 0
    zombie_candidates: list[int] = []

    for case in cases:
        policy = edge_policy if case.use_edge_policy else strict_policy
        result = await run_safe_exec(case.command, policy=policy, timeout_seconds=case.timeout_seconds)
        actual = {
            "status": result.status.value,
            "stdout_truncated": result.stdout_truncated,
            "stderr_truncated": result.stderr_truncated,
            "reason": result.reason,
            "pid": result.pid or -1,
        }
        passed = _status_pass(actual, case)
        if result.status == ExecStatus.TIMEOUT and result.pid:
            zombie_candidates.append(result.pid)
        passes += int(passed)
        print(f"{case.command!r} | {case.expected.value} | {actual['status']} | {'PASS' if passed else 'FAIL'} | {actual['reason']}")

    print("-" * 96)
    print(f"Safety matrix: {passes}/{len(cases)} passed")
    return passes, len(cases), zombie_candidates


async def run_temporal_integration() -> tuple[bool, bool]:
    print("\n=== TB8 Temporal Integration ===")
    ATTEMPT_COUNTER.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        client: Client = env.client
        task_queue = "tb08-safety"

        async with Worker(
            client,
            task_queue=task_queue,
            workflows=[ExecWorkflow],
            activities=[exec_command_activity],
        ):
            blocked_id = str(uuid.uuid4())
            try:
                await client.execute_workflow(
                    ExecWorkflow.run,
                    {
                        "command": "curl http://evil.com",
                        "workspace_dir": str(ROOT),
                        "invocation_id": blocked_id,
                        "raise_on_failure": True,
                        "max_attempts": 5,
                    },
                    id=f"tb08-blocked-{blocked_id}",
                    task_queue=task_queue,
                )
                blocked_non_retryable = False
            except WorkflowFailureError as err:
                cause = getattr(err, "cause", None)
                blocked_non_retryable = False
                while cause:
                    if getattr(cause, "type", None) == "BLOCKED":
                        blocked_non_retryable = True
                        break
                    cause = getattr(cause, "cause", None)

            blocked_attempts = ATTEMPT_COUNTER.get(blocked_id, 0)
            no_retry_for_blocked = blocked_non_retryable and blocked_attempts == 1
            print(f"Blocked command non-retryable: {'PASS' if no_retry_for_blocked else 'FAIL'} (attempts={blocked_attempts})")

            timeout_id = str(uuid.uuid4())
            timeout_result = await client.execute_workflow(
                ExecWorkflow.run,
                {
                    "command": "python3 -c \"import time; time.sleep(60)\"",
                    "workspace_dir": str(ROOT),
                    "invocation_id": timeout_id,
                    "timeout_seconds": 1,
                    "raise_on_failure": False,
                    "max_attempts": 1,
                },
                id=f"tb08-timeout-{timeout_id}",
                task_queue=task_queue,
            )

            pid = int(timeout_result.get("pid") or -1)
            state = _get_process_state(pid)
            timeout_clean_kill = timeout_result.get("status") == ExecStatus.TIMEOUT.value and state in {"not-running", ""}
            print(
                f"Timeout clean kill/no zombie: {'PASS' if timeout_clean_kill else 'FAIL'} "
                f"(status={timeout_result.get('status')}, pid={pid}, ps_state={state})"
            )

            return no_retry_for_blocked, timeout_clean_kill


async def main() -> int:
    matrix_passes, matrix_total, timeout_pids = await run_matrix()

    process_leak_ok = True
    for pid in timeout_pids:
        state = _get_process_state(pid)
        if state not in {"not-running", ""}:
            process_leak_ok = False
            print(f"Potential process leak: pid={pid} state={state}")

    temporal_retry_ok, temporal_timeout_ok = await run_temporal_integration()

    overall = (
        matrix_passes == matrix_total
        and process_leak_ok
        and temporal_retry_ok
        and temporal_timeout_ok
    )

    print("\n=== TB8 Summary ===")
    print(f"Safety matrix: {matrix_passes}/{matrix_total}")
    print(f"Process leak check: {'PASS' if process_leak_ok else 'FAIL'}")
    print(f"Temporal non-retryable BLOCKED: {'PASS' if temporal_retry_ok else 'FAIL'}")
    print(f"Temporal TIMEOUT cleanup: {'PASS' if temporal_timeout_ok else 'FAIL'}")
    print(f"Overall: {'PASS' if overall else 'FAIL'}")

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
