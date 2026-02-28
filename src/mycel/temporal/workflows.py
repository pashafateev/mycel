from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from mycel.temporal.activities import generate_reply_activity
    from mycel.temporal.types import ConversationReply, ConversationRequest


@workflow.defn
class ConversationWorkflow:
    @workflow.run
    async def run(self, request: ConversationRequest) -> ConversationReply:
        reply = await workflow.execute_activity(
            generate_reply_activity,
            request,
            schedule_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )
        return ConversationReply(text=reply)
