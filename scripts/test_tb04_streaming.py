from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import httpx
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tb04.activities import DEFAULT_MODEL
from tb04.transcript import validate_transcript
from tb04.worker import TASK_QUEUE, start_worker
from tb04.workflow import LLMStreamTestWorkflow


@dataclass
class CallSpec:
    request_id: str
    prompt: str
    model: str = DEFAULT_MODEL
    temperature: float = 0.2
    timeout_ms: int = 10_000


class FakeStreamResponse:
    def __init__(
        self,
        lines: list[str],
        *,
        status_code: int = 200,
        body_text: str = "",
        interrupt_after: Optional[int] = None,
        interrupt_exc: Optional[Exception] = None,
    ) -> None:
        self.status_code = status_code
        self._lines = lines
        self._body_text = body_text
        self._interrupt_after = interrupt_after
        self._interrupt_exc = interrupt_exc

    async def aiter_lines(self):
        for idx, line in enumerate(self._lines):
            if self._interrupt_after is not None and idx >= self._interrupt_after:
                raise self._interrupt_exc or httpx.ReadTimeout("simulated stream timeout")
            yield line
            await asyncio.sleep(0)

    async def aread(self) -> bytes:
        return self._body_text.encode()


class FakeStreamContext:
    def __init__(self, response: FakeStreamResponse) -> None:
        self._response = response

    async def __aenter__(self) -> FakeStreamResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _stream_lines_for_text(text: str, *, model: str = DEFAULT_MODEL, tokens: int = 12) -> list[str]:
    chunks = [text[i : i + 12] for i in range(0, len(text), 12)] or [""]
    lines: list[str] = []
    for part in chunks:
        lines.append(
            "data: "
            + json.dumps(
                {
                    "model": model,
                    "choices": [{"delta": {"content": part}}],
                }
            )
        )
    lines.append(
        "data: "
        + json.dumps(
            {
                "model": model,
                "usage": {"prompt_tokens": 6, "completion_tokens": max(1, tokens - 6)},
                "choices": [{"delta": {}}],
            }
        )
    )
    lines.append("data: [DONE]")
    return lines


def _mock_stream(_method: str, _url: str, **kwargs):
    payload = kwargs.get("json") or {}
    messages = payload.get("messages") or []
    prompt = ""
    if messages:
        prompt = str((messages[-1] or {}).get("content", ""))
    timeout = kwargs.get("timeout")
    timeout_ms = 10_000
    if isinstance(timeout, dict):
        timeout_ms = int(float(timeout.get("read", 0)) * 1000)

    if "interrupt" in prompt.lower() or timeout_ms <= 2:
        response = FakeStreamResponse(
            _stream_lines_for_text("partial stream"),
            interrupt_after=1,
            interrupt_exc=httpx.ReadTimeout("simulated stream timeout"),
        )
        return FakeStreamContext(response)

    response_text = f"streamed reply for: {prompt[:40]}"
    return FakeStreamContext(FakeStreamResponse(_stream_lines_for_text(response_text)))


async def _wait_for_result(handle: Any, request_id: str, timeout_s: float = 60.0) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        result = await handle.query(LLMStreamTestWorkflow.get_result, request_id)
        if result:
            return result
        await asyncio.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for result for {request_id}")


async def _run_with_client(client: Client, mock_httpx: bool) -> int:
    workflow_id = f"tb04-stream-{uuid.uuid4().hex[:8]}"

    if mock_httpx and not os.getenv("OPENROUTER_API_KEY"):
        os.environ["OPENROUTER_API_KEY"] = "mock-key"

    patch_ctx = patch("httpx.AsyncClient.stream", side_effect=_mock_stream) if mock_httpx else None

    if patch_ctx:
        patch_ctx.__enter__()

    try:
        async with await start_worker(client, TASK_QUEUE):
            handle = await client.start_workflow(
                LLMStreamTestWorkflow.run,
                {
                    "initial_interval_seconds": 0.2,
                    "maximum_interval_seconds": 1.0,
                    "backoff_coefficient": 2.0,
                    "maximum_attempts": 2,
                },
                id=workflow_id,
                task_queue=TASK_QUEUE,
                execution_timeout=timedelta(minutes=10),
            )

            calls: list[CallSpec] = []
            for i in range(10):
                calls.append(
                    CallSpec(
                        request_id=f"turn-{i:02d}",
                        prompt=f"Turn {i}: give one short reliability sentence.",
                    )
                )
            calls.append(
                CallSpec(
                    request_id="turn-interrupt",
                    prompt="Interrupt this stream on purpose.",
                    timeout_ms=1,
                )
            )

            for call in calls:
                await handle.signal(
                    LLMStreamTestWorkflow.submit_prompt,
                    {
                        "request_id": call.request_id,
                        "prompt": call.prompt,
                        "model": call.model,
                        "temperature": call.temperature,
                        "timeout_ms": call.timeout_ms,
                    },
                )

            results: list[dict[str, Any]] = []
            for call in calls:
                result = await _wait_for_result(handle, call.request_id)
                results.append(result)
                status = "SUCCESS" if result["success"] else "FAIL"
                print(
                    f"{call.request_id}: {status} streamed={result.get('was_streamed')} "
                    f"latency_ms={result['latency_ms']} error={result.get('error_type') or '-'}"
                )

            history = await handle.query(LLMStreamTestWorkflow.get_history)
            validate_transcript(history)

            valid_outcomes = 0
            recoverable_error_types = {"stream_interrupted_error", "timeout_error", "network_error"}
            for result in results:
                if result["success"]:
                    valid_outcomes += 1
                    continue
                if result.get("error_type") in recoverable_error_types:
                    valid_outcomes += 1

            print("\nSummary")
            print(f"total_turns={len(results)}")
            print(f"valid_outcomes={valid_outcomes}")
            print(f"history_items={len(history)}")
            print(f"mocked_httpx={mock_httpx}")

            await handle.signal(LLMStreamTestWorkflow.shutdown)
            await handle.result()

            return 0 if valid_outcomes >= 10 else 1
    finally:
        if patch_ctx:
            patch_ctx.__exit__(None, None, None)


async def run_streaming_scenario(mock_httpx: bool) -> int:
    if mock_httpx:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            return await _run_with_client(env.client, mock_httpx=True)

    client = await Client.connect("localhost:7233")
    return await _run_with_client(client, mock_httpx=False)


def main() -> int:
    mock_httpx = not bool(os.getenv("OPENROUTER_API_KEY"))
    if mock_httpx:
        print("OPENROUTER_API_KEY is not set. Running TB4 streaming with mocked httpx.", flush=True)
    return asyncio.run(run_streaming_scenario(mock_httpx=mock_httpx))


if __name__ == "__main__":
    raise SystemExit(main())
