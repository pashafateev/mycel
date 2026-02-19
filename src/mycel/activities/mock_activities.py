from __future__ import annotations

import asyncio

from temporalio import activity

from mycel.types import LLMRequest, LLMResponse, MemoryUpdateRequest, ToolExecRequest


@activity.defn
async def mock_llm_call(request: LLMRequest) -> LLMResponse:
    """Simulate model routing and an OpenRouter-style completion call."""
    await asyncio.sleep(0.2)

    route_note = f"[{request.model_role}:{request.model_name}]"
    tool_note = f" Tool result: {request.tool_result}" if request.tool_result else ""
    reply = (
        f"{route_note} Mock reply to '{request.user_message}'."
        f" I would route this via OpenRouter using the selected role.{tool_note}"
    )
    return LLMResponse(reply=reply, model_role=request.model_role, model_name=request.model_name)


@activity.defn
async def mock_memory_update(request: MemoryUpdateRequest) -> str:
    """Simulate async memory extraction and persistence."""
    await asyncio.sleep(0.5)
    return (
        f"memory-updated user={request.user_id} request={request.request_id} "
        f"fact='User said: {request.latest_user_message[:40]}'"
    )


@activity.defn
async def mock_tool_exec(request: ToolExecRequest) -> str:
    """Simulate tool execution with retries for flaky operations."""
    attempt = activity.info().attempt
    if request.tool_name == "flaky" and attempt < 2:
        raise RuntimeError("Simulated transient tool failure")

    await asyncio.sleep(0.15)
    return f"tool={request.tool_name} attempt={attempt} payload={request.payload}"
