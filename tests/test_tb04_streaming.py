from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import timedelta
from typing import Optional
from unittest.mock import patch

import httpx
import pytest
from temporalio.testing import WorkflowEnvironment

from tb04.activities import DEFAULT_MODEL
from tb04.transcript import assert_no_orphan_reasoning, validate_transcript
from tb04.worker import TASK_QUEUE, start_worker
from tb04.workflow import LLMStreamTestWorkflow


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
                raise self._interrupt_exc or httpx.ReadTimeout("simulated timeout")
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


class FakePostResponse:
    def __init__(self, payload: dict) -> None:
        self.status_code = 200
        self._payload = payload
        self.text = ""

    def json(self) -> dict:
        return self._payload


def _lines(text: str) -> list[str]:
    return [
        "data: "
        + json.dumps(
            {
                "model": "google/gemini-2.5-flash",
                "choices": [{"delta": {"content": text[:3]}}],
            }
        ),
        "data: "
        + json.dumps(
            {
                "model": "google/gemini-2.5-flash",
                "choices": [{"delta": {"content": text[3:]}}],
            }
        ),
        "data: "
        + json.dumps(
            {
                "model": "google/gemini-2.5-flash",
                "usage": {"total_tokens": 17},
                "choices": [{"delta": {}}],
            }
        ),
        "data: [DONE]",
    ]


async def wait_for_result(handle, request_id: str, timeout_s: float = 10.0):
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        result = await handle.query(LLMStreamTestWorkflow.get_result, request_id)
        if result:
            return result
        await asyncio.sleep(0.05)
    raise TimeoutError(request_id)


@pytest.fixture(autouse=True)
def _api_key() -> None:
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    os.environ["TB4_STREAMING_ENABLED"] = "1"


@pytest.mark.asyncio
async def test_successful_stream_collection() -> None:
    def fake_stream(*args, **kwargs):
        return FakeStreamContext(FakeStreamResponse(_lines("stream-ok")))

    with patch("httpx.AsyncClient.stream", side_effect=fake_stream):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            client = env.client
            async with await start_worker(client, TASK_QUEUE):
                handle = await client.start_workflow(
                    LLMStreamTestWorkflow.run,
                    {
                        "initial_interval_seconds": 0.01,
                        "maximum_interval_seconds": 0.05,
                        "maximum_attempts": 2,
                    },
                    id=f"wf-{uuid.uuid4().hex[:8]}",
                    task_queue=TASK_QUEUE,
                    execution_timeout=timedelta(minutes=1),
                )
                await handle.signal(
                    LLMStreamTestWorkflow.submit_prompt,
                    {"request_id": "req-stream", "prompt": "hello"},
                )
                result = await wait_for_result(handle, "req-stream")
                assert result["success"] is True
                assert result["response_text"] == "stream-ok"
                assert result["token_count"] == 17
                assert result["was_streamed"] is True
                await handle.signal(LLMStreamTestWorkflow.shutdown)
                await handle.result()


@pytest.mark.asyncio
async def test_mid_stream_timeout_returns_recoverable_error() -> None:
    def fake_stream(*args, **kwargs):
        return FakeStreamContext(
            FakeStreamResponse(
                _lines("partial"),
                interrupt_after=1,
                interrupt_exc=httpx.ReadTimeout("simulated timeout"),
            )
        )

    with patch("httpx.AsyncClient.stream", side_effect=fake_stream):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            client = env.client
            async with await start_worker(client, TASK_QUEUE):
                handle = await client.start_workflow(
                    LLMStreamTestWorkflow.run,
                    {
                        "initial_interval_seconds": 0.01,
                        "maximum_interval_seconds": 0.02,
                        "maximum_attempts": 1,
                    },
                    id=f"wf-{uuid.uuid4().hex[:8]}",
                    task_queue=TASK_QUEUE,
                    execution_timeout=timedelta(minutes=1),
                )
                await handle.signal(
                    LLMStreamTestWorkflow.submit_prompt,
                    {"request_id": "req-timeout", "prompt": "interrupt me"},
                )
                result = await wait_for_result(handle, "req-timeout")
                assert result["success"] is False
                assert result["error_type"] == "stream_interrupted_error"
                assert result["was_streamed"] is True
                await handle.signal(LLMStreamTestWorkflow.shutdown)
                await handle.result()


@pytest.mark.asyncio
async def test_streaming_feature_flag_off_uses_non_streaming_path() -> None:
    os.environ["TB4_STREAMING_ENABLED"] = "0"

    def fake_stream(*args, **kwargs):
        raise AssertionError("stream transport should not be called when feature flag is disabled")

    with (
        patch("httpx.AsyncClient.stream", side_effect=fake_stream),
        patch(
            "httpx.AsyncClient.post",
            return_value=FakePostResponse(
                {
                    "model": DEFAULT_MODEL,
                    "choices": [{"message": {"content": "fallback-ok"}}],
                    "usage": {"total_tokens": 11},
                }
            ),
        ),
    ):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            client = env.client
            async with await start_worker(client, TASK_QUEUE):
                handle = await client.start_workflow(
                    LLMStreamTestWorkflow.run,
                    {"initial_interval_seconds": 0.01, "maximum_attempts": 1},
                    id=f"wf-{uuid.uuid4().hex[:8]}",
                    task_queue=TASK_QUEUE,
                    execution_timeout=timedelta(minutes=1),
                )
                await handle.signal(
                    LLMStreamTestWorkflow.submit_prompt,
                    {"request_id": "req-flag-off", "prompt": "hello", "use_stream": True},
                )
                result = await wait_for_result(handle, "req-flag-off")
                assert result["success"] is True
                assert result["response_text"] == "fallback-ok"
                assert result["was_streamed"] is False
                await handle.signal(LLMStreamTestWorkflow.shutdown)
                await handle.result()


@pytest.mark.asyncio
async def test_ten_streamed_turns_with_one_interruption_are_all_valid() -> None:
    interrupted_request_id = "turn-05"

    def fake_stream(*args, **kwargs):
        payload = kwargs.get("json") or {}
        messages = payload.get("messages") or []
        prompt = str((messages[-1] or {}).get("content", "")) if messages else ""
        if interrupted_request_id in prompt:
            return FakeStreamContext(
                FakeStreamResponse(
                    _lines("partial"),
                    interrupt_after=1,
                    interrupt_exc=httpx.ReadTimeout("simulated timeout"),
                )
            )
        turn_label = prompt.split(":", 1)[0]
        return FakeStreamContext(FakeStreamResponse(_lines(f"stream-ok-{turn_label}")))

    with patch("httpx.AsyncClient.stream", side_effect=fake_stream):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            client = env.client
            async with await start_worker(client, TASK_QUEUE):
                handle = await client.start_workflow(
                    LLMStreamTestWorkflow.run,
                    {
                        "initial_interval_seconds": 0.01,
                        "maximum_interval_seconds": 0.05,
                        "maximum_attempts": 1,
                    },
                    id=f"wf-{uuid.uuid4().hex[:8]}",
                    task_queue=TASK_QUEUE,
                    execution_timeout=timedelta(minutes=1),
                )
                request_ids = [f"turn-{idx:02d}" for idx in range(10)]
                for request_id in request_ids:
                    await handle.signal(
                        LLMStreamTestWorkflow.submit_prompt,
                        {
                            "request_id": request_id,
                            "prompt": f"{request_id}: hello",
                            "model": DEFAULT_MODEL,
                            "use_stream": True,
                        },
                    )

                valid_outcomes = 0
                for request_id in request_ids:
                    result = await wait_for_result(handle, request_id)
                    assert "request_id" in result
                    assert isinstance(result["latency_ms"], int)
                    assert isinstance(result["token_count"], int)
                    if result["success"]:
                        assert result["response_text"].startswith("stream-ok-")
                        assert result["was_streamed"] is True
                        valid_outcomes += 1
                    else:
                        assert request_id == interrupted_request_id
                        assert result["error_type"] == "stream_interrupted_error"
                        assert result["was_streamed"] is True
                        valid_outcomes += 1

                history = await handle.query(LLMStreamTestWorkflow.get_history)
                assert validate_transcript(history) == history
                assert valid_outcomes == 10

                await handle.signal(LLMStreamTestWorkflow.shutdown)
                await handle.result()


def test_orphan_reasoning_detection_and_removal(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")
    items = [
        {"type": "message", "role": "user", "content": "hello"},
        {"type": "reasoning", "content": "scratchpad-1"},
        {"type": "reasoning", "content": "scratchpad-2"},
    ]

    cleaned = assert_no_orphan_reasoning(items)
    assert cleaned == [{"type": "message", "role": "user", "content": "hello"}]
    assert "Dropping 2 orphan reasoning item(s)" in caplog.text


def test_valid_reasoning_pairs_pass_validation() -> None:
    items = [
        {"type": "message", "role": "user", "content": "hi"},
        {"type": "reasoning", "content": "think"},
        {"type": "message", "role": "assistant", "content": "done"},
        {"type": "reasoning", "content": "tool decision"},
        {"type": "function_call", "name": "search", "arguments": "{}"},
    ]

    assert validate_transcript(items) == items


def test_invalid_transcript_item_rejected() -> None:
    items = [{"role": "user", "content": "missing type"}]
    with pytest.raises(ValueError, match="missing non-empty type"):
        validate_transcript(items)
