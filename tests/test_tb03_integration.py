from __future__ import annotations

import asyncio
import os
import uuid
from datetime import timedelta
from typing import Optional
from unittest.mock import patch

import httpx
import pytest
from temporalio.testing import WorkflowEnvironment

from tb03.worker import TASK_QUEUE, start_worker
from tb03.workflow import LLMTestWorkflow


class FakeResponse:
    def __init__(
        self, status_code: int, payload: Optional[dict] = None, text: str = ""
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


async def wait_for_result(handle, request_id: str, timeout_s: float = 10.0):
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        result = await handle.query(LLMTestWorkflow.get_result, request_id)
        if result:
            return result
        await asyncio.sleep(0.05)
    raise TimeoutError(request_id)


@pytest.fixture(autouse=True)
def _api_key() -> None:
    os.environ["OPENROUTER_API_KEY"] = "test-key"


@pytest.mark.asyncio
async def test_successful_call() -> None:
    with patch(
        "httpx.AsyncClient.post",
        return_value=FakeResponse(
            200,
            {
                "model": "google/gemini-2.5-flash",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 42},
            },
        ),
    ):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            client = env.client
            async with await start_worker(client, TASK_QUEUE):
                handle = await client.start_workflow(
                    LLMTestWorkflow.run,
                    {
                        "initial_interval_seconds": 0.01,
                        "maximum_interval_seconds": 0.05,
                        "maximum_attempts": 3,
                    },
                    id=f"wf-{uuid.uuid4().hex[:8]}",
                    task_queue=TASK_QUEUE,
                    execution_timeout=timedelta(minutes=1),
                )
                await handle.signal(
                    LLMTestWorkflow.submit_prompt,
                    {"request_id": "req-1", "prompt": "hello"},
                )
                result = await wait_for_result(handle, "req-1")
                assert result["success"] is True
                assert result["response_text"] == "ok"
                assert result["token_count"] == 42
                assert result["retry_count"] == 0
                await handle.signal(LLMTestWorkflow.shutdown)
                await handle.result()


@pytest.mark.asyncio
async def test_retry_on_429_then_success() -> None:
    side_effects = [
        FakeResponse(429, text="rate limited"),
        FakeResponse(
            200,
            {
                "model": "google/gemini-2.5-flash",
                "choices": [{"message": {"content": "after retry"}}],
                "usage": {"total_tokens": 55},
            },
        ),
    ]

    async def fake_post(*args, **kwargs):
        return side_effects.pop(0)

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            client = env.client
            async with await start_worker(client, TASK_QUEUE):
                handle = await client.start_workflow(
                    LLMTestWorkflow.run,
                    {"initial_interval_seconds": 0.01, "maximum_attempts": 3},
                    id=f"wf-{uuid.uuid4().hex[:8]}",
                    task_queue=TASK_QUEUE,
                    execution_timeout=timedelta(minutes=1),
                )
                await handle.signal(
                    LLMTestWorkflow.submit_prompt,
                    {"request_id": "req-429", "prompt": "hello"},
                )
                result = await wait_for_result(handle, "req-429")
                assert result["success"] is True
                assert result["response_text"] == "after retry"
                assert result["retry_count"] == 1
                await handle.signal(LLMTestWorkflow.shutdown)
                await handle.result()


@pytest.mark.asyncio
async def test_retry_on_500_then_success() -> None:
    side_effects = [
        FakeResponse(500, text="server down"),
        FakeResponse(
            200,
            {
                "model": "google/gemini-2.5-flash",
                "choices": [{"message": {"content": "recovered"}}],
                "usage": {"total_tokens": 60},
            },
        ),
    ]

    async def fake_post(*args, **kwargs):
        return side_effects.pop(0)

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            client = env.client
            async with await start_worker(client, TASK_QUEUE):
                handle = await client.start_workflow(
                    LLMTestWorkflow.run,
                    {"initial_interval_seconds": 0.01, "maximum_attempts": 3},
                    id=f"wf-{uuid.uuid4().hex[:8]}",
                    task_queue=TASK_QUEUE,
                    execution_timeout=timedelta(minutes=1),
                )
                await handle.signal(
                    LLMTestWorkflow.submit_prompt,
                    {"request_id": "req-500", "prompt": "hello"},
                )
                result = await wait_for_result(handle, "req-500")
                assert result["success"] is True
                assert result["response_text"] == "recovered"
                assert result["retry_count"] == 1
                await handle.signal(LLMTestWorkflow.shutdown)
                await handle.result()


@pytest.mark.asyncio
async def test_timeout_failure_after_retries() -> None:
    async def fake_post(*args, **kwargs):
        raise httpx.ReadTimeout("simulated timeout")

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            client = env.client
            async with await start_worker(client, TASK_QUEUE):
                handle = await client.start_workflow(
                    LLMTestWorkflow.run,
                    {"initial_interval_seconds": 0.01, "maximum_attempts": 2},
                    id=f"wf-{uuid.uuid4().hex[:8]}",
                    task_queue=TASK_QUEUE,
                    execution_timeout=timedelta(minutes=1),
                )
                await handle.signal(
                    LLMTestWorkflow.submit_prompt,
                    {"request_id": "req-timeout", "prompt": "hello"},
                )
                result = await wait_for_result(handle, "req-timeout")
                assert result["success"] is False
                assert result["error_type"] == "timeout_error"
                assert result["retry_count"] == 1
                await handle.signal(LLMTestWorkflow.shutdown)
                await handle.result()
