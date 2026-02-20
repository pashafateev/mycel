from __future__ import annotations

import asyncio

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from tb01.workflows import PingWorkflow, pong_activity


@pytest.mark.asyncio
async def test_ping_workflow_signal_and_query() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="tb01-test-queue",
            workflows=[PingWorkflow],
            activities=[pong_activity],
        ):
            handle = await env.client.start_workflow(
                PingWorkflow.run,
                id="tb01-test-workflow",
                task_queue="tb01-test-queue",
            )

            request_id = "req-1"
            await handle.signal(
                PingWorkflow.enqueue_ping,
                {"request_id": request_id, "message": "hello"},
            )

            response = None
            for _ in range(50):
                response = await handle.query(PingWorkflow.get_response, request_id)
                if response is not None:
                    break
                await asyncio.sleep(0.05)

            assert response == "pong: hello"
