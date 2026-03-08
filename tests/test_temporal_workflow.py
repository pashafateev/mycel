from __future__ import annotations

import asyncio
import uuid

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import mycel.temporal.workflows as workflow_module
from mycel.temporal.types import ConversationReply, ConversationRequest, LLMTurnRequest, LLMTurnResponse, ToolExecutionRequest
from mycel.temporal.workflows import ConversationWorkflow
from mycel.tools.registry import MAX_TOOL_DEPTH


def test_conversation_workflow_happy_path() -> None:
    asyncio.run(_run_happy_path())


def test_conversation_workflow_stops_at_max_tool_depth() -> None:
    asyncio.run(_run_max_depth_path())


async def _run_happy_path() -> None:
    requests: list[LLMTurnRequest] = []

    @activity.defn(name="decide_next_step_activity")
    async def fake_decide(request: LLMTurnRequest) -> LLMTurnResponse:
        requests.append(request)
        if len(requests) == 1:
            return LLMTurnResponse(
                type="tool_call",
                tool_name="read_file",
                arguments={"path": "notes.txt"},
            )
        return LLMTurnResponse(type="final", text="Final answer after tool")

    @activity.defn(name="execute_tool_activity")
    async def fake_execute(request: ToolExecutionRequest) -> str:
        assert request.tool.name == "read_file"
        assert request.tool.arguments == {"path": "notes.txt"}
        return "notes body"

    await _run_workflow_test(
        fake_decide=fake_decide,
        fake_execute=fake_execute,
        assertions=lambda reply: _assert_happy_path(reply, requests),
    )


async def _run_max_depth_path() -> None:
    llm_calls = 0
    tool_calls = 0

    @activity.defn(name="decide_next_step_activity")
    async def fake_decide(request: LLMTurnRequest) -> LLMTurnResponse:
        nonlocal llm_calls
        llm_calls += 1
        return LLMTurnResponse(
            type="tool_call",
            tool_name="memory_note",
            arguments={"text": f"loop-{llm_calls}"},
        )

    @activity.defn(name="execute_tool_activity")
    async def fake_execute(request: ToolExecutionRequest) -> str:
        nonlocal tool_calls
        tool_calls += 1
        return f"stored {request.tool.arguments['text']}"

    def assertions(reply: ConversationReply) -> None:
        assert reply.text == f"Tool loop stopped after {MAX_TOOL_DEPTH} calls in one turn."
        assert tool_calls == MAX_TOOL_DEPTH
        assert llm_calls == MAX_TOOL_DEPTH + 1

    await _run_workflow_test(
        fake_decide=fake_decide,
        fake_execute=fake_execute,
        assertions=assertions,
    )


async def _run_workflow_test(*, fake_decide, fake_execute, assertions) -> None:
    original_decide = workflow_module.decide_next_step_activity
    original_execute = workflow_module.execute_tool_activity
    workflow_module.decide_next_step_activity = fake_decide
    workflow_module.execute_tool_activity = fake_execute

    try:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-mycel",
                workflows=[ConversationWorkflow],
                activities=[fake_decide, fake_execute],
            ):
                reply = await env.client.execute_workflow(
                    ConversationWorkflow.run,
                    ConversationRequest(user_id=1, text="hello"),
                    id=f"wf-{uuid.uuid4()}",
                    task_queue="test-mycel",
                    result_type=ConversationReply,
                )
                assertions(reply)
    finally:
        workflow_module.decide_next_step_activity = original_decide
        workflow_module.execute_tool_activity = original_execute


def _assert_happy_path(reply: ConversationReply, requests: list[LLMTurnRequest]) -> None:
    assert reply.text == "Final answer after tool"
    assert len(requests) == 2
    assert requests[0].messages == [workflow_module.ConversationMessage(role="user", content="hello")]
    assert requests[1].messages[-1].role == "tool"
    assert "notes body" in requests[1].messages[-1].content
