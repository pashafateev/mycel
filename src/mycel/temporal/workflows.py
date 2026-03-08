from __future__ import annotations

import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from mycel.temporal.activities import decide_next_step_activity, execute_tool_activity
    from mycel.temporal.types import (
        ConversationMessage,
        ConversationReply,
        ConversationRequest,
        LLMTurnRequest,
        ToolExecutionRequest,
    )
    from mycel.tools.registry import MAX_TOOL_DEPTH, validate_tool_call


_ACTIVITY_TIMEOUT = timedelta(seconds=120)
_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
)


@workflow.defn
class ConversationWorkflow:
    @workflow.run
    async def run(self, request: ConversationRequest) -> ConversationReply:
        messages = [ConversationMessage(role="user", content=request.text)]
        tool_depth = 0

        while True:
            decision = await workflow.execute_activity(
                decide_next_step_activity,
                LLMTurnRequest(messages=messages),
                schedule_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )

            if decision.type == "final":
                return ConversationReply(text=decision.text or "")

            try:
                validated_tool = validate_tool_call(decision)
            except ValueError as exc:
                return ConversationReply(text=f"Tool request rejected: {exc}")

            if tool_depth >= MAX_TOOL_DEPTH:
                return ConversationReply(text=_tool_depth_limit_message())

            messages.append(
                ConversationMessage(
                    role="assistant",
                    content=_render_tool_call_message(validated_tool.name, validated_tool.arguments),
                )
            )

            tool_result = await workflow.execute_activity(
                execute_tool_activity,
                ToolExecutionRequest(tool=validated_tool),
                schedule_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            tool_depth += 1
            messages.append(
                ConversationMessage(
                    role="tool",
                    content=f"{validated_tool.name} result:\n{tool_result}",
                )
            )


def _render_tool_call_message(name: str, arguments: dict[str, object]) -> str:
    return f"Calling tool {name} with arguments: {json.dumps(arguments, sort_keys=True)}"


def _tool_depth_limit_message() -> str:
    return f"Tool loop stopped after {MAX_TOOL_DEPTH} calls in one turn."
