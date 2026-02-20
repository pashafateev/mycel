from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from .activities import DEFAULT_MODEL, stream_llm
    from .transcript import validate_transcript


@dataclass
class _LLMRequest:
    request_id: str
    prompt: str
    model: str
    temperature: float
    timeout_ms: int


@workflow.defn
class LLMStreamTestWorkflow:
    def __init__(self) -> None:
        self._queue: list[_LLMRequest] = []
        self._results: dict[str, dict[str, Any]] = {}
        self._history: list[dict[str, Any]] = []
        self._shutdown = False
        self._retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=8),
            maximum_attempts=3,
        )

    @workflow.run
    async def run(self, retry_config: Optional[dict[str, Any]] = None) -> None:
        if retry_config:
            self._retry_policy = RetryPolicy(
                initial_interval=timedelta(
                    seconds=float(retry_config.get("initial_interval_seconds", 1.0))
                ),
                backoff_coefficient=float(retry_config.get("backoff_coefficient", 2.0)),
                maximum_interval=timedelta(
                    seconds=float(retry_config.get("maximum_interval_seconds", 8.0))
                ),
                maximum_attempts=int(retry_config.get("maximum_attempts", 3)),
            )

        while True:
            await workflow.wait_condition(lambda: bool(self._queue) or self._shutdown)
            while self._queue:
                req = self._queue.pop(0)
                await self._process_request(req)
            if self._shutdown:
                return

    @workflow.signal
    async def submit_prompt(self, request: dict[str, Any]) -> None:
        request_id = str(request["request_id"])
        prompt = str(request.get("prompt", ""))
        model = str(request.get("model", DEFAULT_MODEL))
        temperature = float(request.get("temperature", 0.2))
        timeout_ms = int(request.get("timeout_ms", 10_000))
        self._queue.append(
            _LLMRequest(
                request_id=request_id,
                prompt=prompt,
                model=model,
                temperature=temperature,
                timeout_ms=timeout_ms,
            )
        )

    @workflow.signal
    async def append_history_items(self, items: list[dict[str, Any]]) -> None:
        self._history.extend(items)

    @workflow.signal
    async def shutdown(self) -> None:
        self._shutdown = True

    @workflow.query
    def get_result(self, request_id: str) -> Optional[dict[str, Any]]:
        return self._results.get(request_id)

    @workflow.query
    def get_results(self) -> dict[str, dict[str, Any]]:
        return self._results

    @workflow.query
    def get_history(self) -> list[dict[str, Any]]:
        return self._history

    async def _process_request(self, req: _LLMRequest) -> None:
        start_time = workflow.now()
        try:
            self._history = validate_transcript(self._history)
        except ValueError as exc:
            elapsed_ms = int((workflow.now() - start_time).total_seconds() * 1000)
            self._results[req.request_id] = {
                "request_id": req.request_id,
                "success": False,
                "response_text": "",
                "model_used": req.model,
                "token_count": 0,
                "latency_ms": elapsed_ms,
                "retry_count": 0,
                "error_type": "invalid_transcript_error",
                "error_message": str(exc),
                "was_streamed": True,
            }
            return

        self._history.append({"type": "message", "role": "user", "content": req.prompt})

        try:
            result = await workflow.execute_activity(
                stream_llm,
                args=[
                    req.model,
                    self._history,
                    req.temperature,
                    req.timeout_ms,
                ],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=self._retry_policy,
            )
            response_text = result.get("response_text", "")
            self._history.append(
                {"type": "message", "role": "assistant", "content": response_text}
            )
            self._results[req.request_id] = {
                "request_id": req.request_id,
                "success": True,
                "response_text": response_text,
                "model_used": result.get("model_used", req.model),
                "token_count": int(result.get("token_count", 0)),
                "latency_ms": int(result.get("latency_ms", 0)),
                "retry_count": max(0, int(result.get("attempt", 1)) - 1),
                "error_type": None,
                "was_streamed": bool(result.get("was_streamed", False)),
            }
        except ActivityError as exc:
            error_type = "activity_error"
            attempt = 1
            message = str(exc)

            cause = exc.cause
            if isinstance(cause, ApplicationError):
                if cause.type:
                    error_type = cause.type
                if cause.details:
                    first = cause.details[0]
                    if isinstance(first, dict):
                        attempt = int(first.get("attempt", attempt))
                message = cause.message

            elapsed_ms = int((workflow.now() - start_time).total_seconds() * 1000)
            self._results[req.request_id] = {
                "request_id": req.request_id,
                "success": False,
                "response_text": "",
                "model_used": req.model,
                "token_count": 0,
                "latency_ms": elapsed_ms,
                "retry_count": max(0, attempt - 1),
                "error_type": error_type,
                "error_message": message,
                "was_streamed": True,
            }
