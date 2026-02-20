from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash"


def _extract_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""

    message = (choices[0] or {}).get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)

    return ""


def _tokens(payload: dict[str, Any]) -> int:
    usage = payload.get("usage") or {}
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return total

    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
        return prompt_tokens + completion_tokens

    return 0


def _app_error(
    message: str,
    *,
    error_type: str,
    non_retryable: bool,
    attempt: int,
    status_code: int | None = None,
) -> ApplicationError:
    details = {"error_type": error_type, "attempt": attempt}
    if status_code is not None:
        details["status_code"] = status_code
    return ApplicationError(
        message,
        details,
        type=error_type,
        non_retryable=non_retryable,
    )


@activity.defn
async def call_llm(
    model: str = DEFAULT_MODEL,
    messages: Optional[list[dict[str, str]]] = None,
    temperature: float = 0.2,
    timeout_ms: int = 10_000,
) -> dict[str, Any]:
    """Call OpenRouter chat completions API and return normalized response metadata."""
    attempt = activity.info().attempt
    started_at = time.perf_counter()

    if not messages:
        raise _app_error(
            "messages cannot be empty",
            error_type="validation_error",
            non_retryable=True,
            attempt=attempt,
        )

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise _app_error(
            "OPENROUTER_API_KEY is not set",
            error_type="auth_error",
            non_retryable=True,
            attempt=attempt,
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
    }

    try:
        timeout = httpx.Timeout(timeout_ms / 1000)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise _app_error(
            f"OpenRouter request timed out: {exc}",
            error_type="timeout_error",
            non_retryable=False,
            attempt=attempt,
        ) from exc
    except httpx.RequestError as exc:
        raise _app_error(
            f"OpenRouter request failed: {exc}",
            error_type="network_error",
            non_retryable=False,
            attempt=attempt,
        ) from exc

    if response.status_code in (401, 403):
        raise _app_error(
            "OpenRouter authentication failed",
            error_type="auth_error",
            non_retryable=True,
            attempt=attempt,
            status_code=response.status_code,
        )
    if response.status_code == 429:
        raise _app_error(
            "OpenRouter rate limit",
            error_type="rate_limit_error",
            non_retryable=False,
            attempt=attempt,
            status_code=response.status_code,
        )
    if 500 <= response.status_code <= 599:
        raise _app_error(
            "OpenRouter server error",
            error_type="server_error",
            non_retryable=False,
            attempt=attempt,
            status_code=response.status_code,
        )
    if response.status_code == 400:
        raise _app_error(
            f"OpenRouter bad request: {response.text}",
            error_type="invalid_request_error",
            non_retryable=True,
            attempt=attempt,
            status_code=response.status_code,
        )
    if response.status_code >= 400:
        raise _app_error(
            f"OpenRouter unexpected error: {response.text}",
            error_type="http_error",
            non_retryable=True,
            attempt=attempt,
            status_code=response.status_code,
        )

    data = response.json()
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    return {
        "response_text": _extract_text(data),
        "model_used": data.get("model") or payload["model"],
        "token_count": _tokens(data),
        "latency_ms": latency_ms,
        "attempt": attempt,
    }
