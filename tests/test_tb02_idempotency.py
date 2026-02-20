from __future__ import annotations

import asyncio
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from tb01.bot import BotDeps, replay_update_payload
from tb01.workflows import PingWorkflow, pong_activity


def _build_payload(update_id: int, message_id: int, text: str, chat_id: int = 4242) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


@pytest.mark.asyncio
async def test_tb02_idempotency_with_temporal_environment() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="tb02-test-queue",
            workflows=[PingWorkflow],
            activities=[pong_activity],
        ):
            handle = await env.client.start_workflow(
                PingWorkflow.run,
                id="tb02-idempotency-workflow",
                task_queue="tb02-test-queue",
            )

            deps = BotDeps(workflow_handle=handle)
            unique_payloads = [
                _build_payload(9000 + i, i + 1, f"msg-{i + 1}") for i in range(10)
            ]
            unique_payloads[3], unique_payloads[4], unique_payloads[5] = (
                unique_payloads[5],
                unique_payloads[3],
                unique_payloads[4],
            )
            duplicate_payloads = [
                unique_payloads[2],
                unique_payloads[5],
                unique_payloads[8],
            ]
            replay_stream = unique_payloads + duplicate_payloads

            for payload in replay_stream:
                envelope = await replay_update_payload(payload, deps)
                if envelope is None:
                    continue
                await handle.signal(PingWorkflow.enqueue_ping, envelope)

            stats = None
            for _ in range(100):
                stats = await handle.query(PingWorkflow.get_signal_stats)
                if stats["response_count"] == 10:
                    break
                await asyncio.sleep(0.05)

            assert stats is not None
            assert len(deps.tracker.seen_update_ids) == 10
            assert stats["processed_signals"] == 10
            assert stats["response_count"] == 10
            assert stats["out_of_order_count"] >= 1

            request_ids = await handle.query(PingWorkflow.get_processed_request_ids)
            assert len(request_ids) == 10
            assert len(set(request_ids)) == 10
