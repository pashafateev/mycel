from __future__ import annotations

from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from mycel.activities.mock_activities import (
        mock_llm_call,
        mock_memory_update,
        mock_tool_exec,
    )
    from mycel.types import (
        ConversationInput,
        ConversationTurn,
        LLMRequest,
        MemoryUpdateRequest,
        MessageEnvelope,
        ToolExecRequest,
    )


@workflow.defn
class ConversationWorkflow:
    def __init__(self) -> None:
        self._user_id = ""
        self._pending_messages: list[MessageEnvelope] = []
        self._history: list[ConversationTurn] = []
        self._turn_count = 0
        self._max_turns_before_continue_as_new = 8
        self._responses: dict[str, str] = {}

    @workflow.run
    async def run(self, args: ConversationInput) -> None:
        self._user_id = args.user_id
        self._pending_messages = list(args.pending_messages)
        self._history = list(args.history)
        self._turn_count = args.turn_count
        self._max_turns_before_continue_as_new = args.max_turns_before_continue_as_new

        while True:
            await workflow.wait_condition(lambda: len(self._pending_messages) > 0)
            envelope = self._pending_messages.pop(0)
            await self._process_turn(envelope)

            if self._turn_count >= self._max_turns_before_continue_as_new:
                workflow.continue_as_new(
                    ConversationInput(
                        user_id=self._user_id,
                        pending_messages=self._pending_messages,
                        history=self._history[-(self._max_turns_before_continue_as_new * 2) :],
                        turn_count=self._turn_count,
                        max_turns_before_continue_as_new=self._max_turns_before_continue_as_new,
                    )
                )

    @workflow.signal
    async def add_user_message(self, envelope: MessageEnvelope) -> None:
        self._pending_messages.append(envelope)

    @workflow.query
    def get_response(self, request_id: str) -> Optional[str]:
        return self._responses.get(request_id)

    async def _process_turn(self, envelope: MessageEnvelope) -> None:
        self._turn_count += 1
        self._history.append(
            ConversationTurn(
                role="user",
                text=envelope.text,
                request_id=envelope.request_id,
            )
        )

        maybe_tool_result = None
        if envelope.text.startswith("/tool "):
            maybe_tool_result = await workflow.execute_activity(
                mock_tool_exec,
                ToolExecRequest(
                    request_id=envelope.request_id,
                    tool_name="flaky",
                    payload={"raw": envelope.text},
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=3),
            )

        role, model = self._route_model(envelope.text)
        llm_result = await workflow.execute_activity(
            mock_llm_call,
            LLMRequest(
                request_id=envelope.request_id,
                user_id=self._user_id,
                model_role=role,
                model_name=model,
                history=[{"role": t.role, "text": t.text} for t in self._history[-8:]],
                user_message=envelope.text,
                tool_result=maybe_tool_result,
            ),
            start_to_close_timeout=timedelta(seconds=15),
        )

        assistant_reply = llm_result.reply
        self._history.append(
            ConversationTurn(
                role="assistant",
                text=assistant_reply,
                request_id=envelope.request_id,
            )
        )
        self._responses[envelope.request_id] = assistant_reply

        # Fire-and-forget memory extraction so reply availability is not blocked.
        workflow.start_activity(
            mock_memory_update,
            MemoryUpdateRequest(
                user_id=self._user_id,
                request_id=envelope.request_id,
                latest_user_message=envelope.text,
                latest_assistant_message=assistant_reply,
            ),
            start_to_close_timeout=timedelta(seconds=20),
            retry_policy=RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=2),
        )

    def _route_model(self, text: str) -> tuple[str, str]:
        lowered = text.lower()
        if any(keyword in lowered for keyword in ("architecture", "strategy", "deep")):
            return ("executive", "mock/executive-reasoning")
        if any(keyword in lowered for keyword in ("debug", "review", "complex")):
            return ("senior", "mock/senior-smart")
        return ("junior", "mock/junior-fast")
