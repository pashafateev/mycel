from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from temporalio import activity, workflow


@activity.defn
async def pong_activity(message: str) -> str:
    return f"pong: {message}"


@workflow.defn
class PingWorkflow:
    def __init__(self) -> None:
        self._pending: list[dict[str, Any]] = []
        self._responses: dict[str, str] = {}
        self._last_seq_by_chat: dict[str, int] = {}
        self._out_of_order_events: list[dict[str, Any]] = []
        self._processed_signals: int = 0

    @workflow.run
    async def run(self) -> None:
        while True:
            await workflow.wait_condition(lambda: len(self._pending) > 0)
            payload = self._pending.pop(0)
            request_id = payload["request_id"]
            message = payload["message"]
            chat_id = payload.get("chat_id")
            sequence = payload.get("sequence")

            if chat_id is not None and sequence is not None:
                chat_key = str(chat_id)
                sequence_value = int(sequence)
                last_seen = self._last_seq_by_chat.get(chat_key, 0)
                expected = last_seen + 1
                if sequence_value != expected:
                    workflow.logger.warning(
                        "Out-of-order signal for chat_id=%s: got sequence=%d expected=%d",
                        chat_key,
                        sequence_value,
                        expected,
                    )
                    self._out_of_order_events.append(
                        {
                            "chat_id": chat_key,
                            "sequence": sequence_value,
                            "expected": expected,
                        }
                    )
                    if len(self._out_of_order_events) > 200:
                        self._out_of_order_events.pop(0)
                self._last_seq_by_chat[chat_key] = max(last_seen, sequence_value)

            response = await workflow.execute_activity(
                pong_activity,
                message,
                start_to_close_timeout=timedelta(seconds=10),
            )
            self._responses[request_id] = response
            self._processed_signals += 1

            # Keep memory bounded for the spike.
            if len(self._responses) > 200:
                oldest = next(iter(self._responses))
                del self._responses[oldest]

    @workflow.signal
    def enqueue_ping(self, payload: dict[str, Any]) -> None:
        self._pending.append(payload)

    @workflow.query
    def get_response(self, request_id: str) -> Optional[str]:
        return self._responses.get(request_id)

    @workflow.query
    def get_processed_request_ids(self) -> list[str]:
        return list(self._responses.keys())

    @workflow.query
    def get_signal_stats(self) -> dict[str, Any]:
        return {
            "processed_signals": self._processed_signals,
            "response_count": len(self._responses),
            "last_seq_by_chat": dict(self._last_seq_by_chat),
            "out_of_order_count": len(self._out_of_order_events),
            "out_of_order_events": list(self._out_of_order_events),
        }
