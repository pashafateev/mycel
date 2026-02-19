from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from mycel.activities.mock_activities import mock_llm_call, mock_memory_update, mock_tool_exec
from mycel.types import ConversationInput, MessageEnvelope
from mycel.workflows import ConversationWorkflow


@pytest_asyncio.fixture
async def temporal_client_and_queue() -> tuple[Client, str]:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        task_queue = f"mycel-test-{uuid.uuid4().hex[:8]}"
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[ConversationWorkflow],
            activities=[mock_llm_call, mock_memory_update, mock_tool_exec],
        ):
            yield env.client, task_queue


async def _wait_for_response(handle, request_id: str, timeout_s: float = 8.0) -> str:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        response = await handle.query(ConversationWorkflow.get_response, request_id)
        if response:
            return response
        await asyncio.sleep(0.1)
    raise AssertionError(f"Timed out waiting for response request_id={request_id}")


@pytest.mark.asyncio
async def test_send_message_get_reply(temporal_client_and_queue: tuple[Client, str]) -> None:
    client, task_queue = temporal_client_and_queue

    handle = await client.start_workflow(
        ConversationWorkflow.run,
        ConversationInput(user_id="user-1", pending_messages=[]),
        id=f"conversation-{uuid.uuid4().hex[:8]}",
        task_queue=task_queue,
    )

    request_id = "req-1"
    await handle.signal(
        ConversationWorkflow.add_user_message,
        MessageEnvelope(request_id=request_id, user_id="user-1", text="hello temporal"),
    )

    reply = await _wait_for_response(handle, request_id)
    assert "Mock reply to 'hello temporal'" in reply

    await client.get_workflow_handle(handle.id).terminate("test cleanup")


@pytest.mark.asyncio
async def test_continue_as_new_triggers_after_n_turns(
    temporal_client_and_queue: tuple[Client, str],
) -> None:
    client, task_queue = temporal_client_and_queue

    workflow_id = f"conversation-{uuid.uuid4().hex[:8]}"
    handle = await client.start_workflow(
        ConversationWorkflow.run,
        ConversationInput(
            user_id="user-2",
            pending_messages=[MessageEnvelope(request_id="req-ca-1", user_id="user-2", text="first")],
            max_turns_before_continue_as_new=1,
        ),
        id=workflow_id,
        task_queue=task_queue,
    )
    start_run_handle = client.get_workflow_handle(workflow_id, run_id=handle.first_execution_run_id)

    deadline = asyncio.get_running_loop().time() + 8.0
    continued_as_new = False
    while asyncio.get_running_loop().time() < deadline and not continued_as_new:
        history = await start_run_handle.fetch_history()
        continued_as_new = any(
            event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CONTINUED_AS_NEW
            for event in history.events
        )
        if not continued_as_new:
            await asyncio.sleep(0.1)

    assert continued_as_new, "Workflow did not Continue-As-New"

    await client.get_workflow_handle(workflow_id).terminate("test cleanup")


@pytest.mark.asyncio
async def test_memory_update_activity_fires_after_turn(
    temporal_client_and_queue: tuple[Client, str],
) -> None:
    client, task_queue = temporal_client_and_queue

    workflow_id = f"conversation-{uuid.uuid4().hex[:8]}"
    handle = await client.start_workflow(
        ConversationWorkflow.run,
        ConversationInput(user_id="user-3", pending_messages=[]),
        id=workflow_id,
        task_queue=task_queue,
    )

    await handle.signal(
        ConversationWorkflow.add_user_message,
        MessageEnvelope(request_id="req-mem-1", user_id="user-3", text="remember that I like coffee"),
    )
    await _wait_for_response(handle, "req-mem-1")

    deadline = asyncio.get_running_loop().time() + 8.0
    saw_memory_activity = False
    while asyncio.get_running_loop().time() < deadline and not saw_memory_activity:
        history = await handle.fetch_history()
        saw_memory_activity = any(
            event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
            and event.activity_task_scheduled_event_attributes.activity_type.name == "mock_memory_update"
            for event in history.events
        )
        if not saw_memory_activity:
            await asyncio.sleep(0.1)

    assert saw_memory_activity, "mock_memory_update activity was never scheduled"

    await client.get_workflow_handle(workflow_id).terminate("test cleanup")
