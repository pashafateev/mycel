from __future__ import annotations

from datetime import timedelta
from typing import Optional

from temporalio import activity, workflow


@activity.defn
async def pong_activity(message: str) -> str:
    return f"pong: {message}"


@workflow.defn
class PingWorkflow:
    def __init__(self) -> None:
        self._pending: list[dict[str, str]] = []
        self._responses: dict[str, str] = {}

    @workflow.run
    async def run(self) -> None:
        while True:
            await workflow.wait_condition(lambda: len(self._pending) > 0)
            payload = self._pending.pop(0)
            request_id = payload["request_id"]
            message = payload["message"]
            response = await workflow.execute_activity(
                pong_activity,
                message,
                start_to_close_timeout=timedelta(seconds=10),
            )
            self._responses[request_id] = response

            # Keep memory bounded for the spike.
            if len(self._responses) > 200:
                oldest = next(iter(self._responses))
                del self._responses[oldest]

    @workflow.signal
    def enqueue_ping(self, payload: dict[str, str]) -> None:
        self._pending.append(payload)

    @workflow.query
    def get_response(self, request_id: str) -> Optional[str]:
        return self._responses.get(request_id)
