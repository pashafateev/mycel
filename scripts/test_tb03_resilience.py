from __future__ import annotations

import asyncio
import os
import statistics
import subprocess
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio.client import Client

from tb03.activities import DEFAULT_MODEL
from tb03.worker import TASK_QUEUE, start_worker
from tb03.workflow import LLMTestWorkflow


@dataclass
class CallSpec:
    request_id: str
    prompt: str
    model: str = DEFAULT_MODEL
    temperature: float = 0.2
    timeout_ms: int = 10_000


async def _wait_for_result(handle: Any, request_id: str, timeout_s: float = 60.0) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        result = await handle.query(LLMTestWorkflow.get_result, request_id)
        if result:
            return result
        await asyncio.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for result for {request_id}")


def _pct(data: list[int], pct: float) -> int:
    if not data:
        return 0
    if len(data) == 1:
        return data[0]
    ordered = sorted(data)
    idx = min(len(ordered) - 1, round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[idx]


async def run_real_resilience() -> int:
    client = await Client.connect("localhost:7233")
    workflow_id = f"tb03-resilience-{uuid.uuid4().hex[:8]}"

    async with await start_worker(client, TASK_QUEUE):
        handle = await client.start_workflow(
            LLMTestWorkflow.run,
            {
                "initial_interval_seconds": 0.2,
                "maximum_interval_seconds": 1.0,
                "backoff_coefficient": 2.0,
                "maximum_attempts": 3,
            },
            id=workflow_id,
            task_queue=TASK_QUEUE,
            execution_timeout=timedelta(minutes=10),
        )

        calls: list[CallSpec] = []
        for i in range(25):
            calls.append(
                CallSpec(
                    request_id=f"req-{i:02d}",
                    prompt=f"Return one short sentence about reliability test #{i}.",
                )
            )

        # Fault injection set
        calls[0].timeout_ms = 50
        calls[1].timeout_ms = 50
        calls[2].model = "invalid/model-name"
        calls[3].model = "invalid/model-name"
        calls[4].prompt = ""

        results: list[dict[str, Any]] = []
        for call in calls:
            await handle.signal(
                LLMTestWorkflow.submit_prompt,
                {
                    "request_id": call.request_id,
                    "prompt": call.prompt,
                    "model": call.model,
                    "temperature": call.temperature,
                    "timeout_ms": call.timeout_ms,
                },
            )

        for call in calls:
            result = await _wait_for_result(handle, call.request_id)
            results.append(result)
            status = "SUCCESS" if result["success"] else "FAIL"
            error_type = result.get("error_type") or "-"
            print(
                f"{call.request_id}: {status} latency_ms={result['latency_ms']} "
                f"retries={result['retry_count']} error={error_type}"
            )

        await handle.signal(LLMTestWorkflow.shutdown)
        await handle.result()

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    success_rate = (len(successes) / len(results)) * 100.0 if results else 0.0
    latency_values = [int(r["latency_ms"]) for r in successes]

    print("\nSummary")
    print(f"total_calls={len(results)}")
    print(f"success_rate={success_rate:.1f}% ({len(successes)}/{len(results)})")
    print(f"latency_p50_ms={_pct(latency_values, 50)}")
    print(f"latency_p95_ms={_pct(latency_values, 95)}")
    print(f"latency_max_ms={max(latency_values) if latency_values else 0}")
    print(
        "avg_retry_count="
        f"{statistics.mean([r['retry_count'] for r in results]) if results else 0:.2f}"
    )

    error_counts = Counter(r.get("error_type") for r in failures)
    print("error_breakdown=")
    if error_counts:
        for error_type, count in sorted(error_counts.items()):
            print(f"  {error_type}: {count}")
    else:
        print("  none")

    return 0


def run_mock_only() -> int:
    print("OPENROUTER_API_KEY is not set. Skipping real OpenRouter calls.", flush=True)
    print("Running mocked Temporal integration tests instead...", flush=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_tb03_integration.py"],
        check=False,
    )
    return proc.returncode


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        return run_mock_only()
    return asyncio.run(run_real_resilience())


if __name__ == "__main__":
    raise SystemExit(main())
