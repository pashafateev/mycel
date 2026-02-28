from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator, Optional

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash"
STREAMING_MODEL = DEFAULT_MODEL
STREAMING_FEATURE_FLAG = "TB4_STREAMING_ENABLED"


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


def _extract_delta_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""

    delta = (choices[0] or {}).get("delta") or {}
    content = delta.get("content")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    return ""


def _env_flag_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def _post_completion(
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    payload: dict[str, Any],
    attempt: int,
) -> dict[str, Any]:
    response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
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
    return response.json()


async def _iter_stream_chunks(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    async for line in response.aiter_lines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue

        data = stripped[5:].strip()
        if data == "[DONE]":
            return

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict):
            yield payload


@activity.defn
async def stream_llm(
    model: str = DEFAULT_MODEL,
    messages: Optional[list[dict[str, Any]]] = None,
    temperature: float = 0.2,
    timeout_ms: int = 10_000,
    use_stream: bool = True,
) -> dict[str, Any]:
    """Collect a streamed OpenRouter response and return the complete normalized result."""
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

    collected_text: list[str] = []
    model_used = payload["model"]
    can_stream = (
        use_stream
        and _env_flag_enabled(STREAMING_FEATURE_FLAG, default=False)
        and model_used == STREAMING_MODEL
    )

    try:
        timeout = httpx.Timeout(timeout_ms / 1000)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if can_stream:
                usage_payload: dict[str, Any] = {}
                stream_payload = dict(payload)
                stream_payload["stream"] = True
                stream_payload["stream_options"] = {"include_usage": True}
                async with client.stream(
                    "POST", OPENROUTER_URL, headers=headers, json=stream_payload
                ) as response:
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
                        body = await response.aread()
                        raise _app_error(
                            f"OpenRouter bad request: {body.decode(errors='replace')}",
                            error_type="invalid_request_error",
                            non_retryable=True,
                            attempt=attempt,
                            status_code=response.status_code,
                        )
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise _app_error(
                            f"OpenRouter unexpected error: {body.decode(errors='replace')}",
                            error_type="http_error",
                            non_retryable=True,
                            attempt=attempt,
                            status_code=response.status_code,
                        )

                    async for chunk in _iter_stream_chunks(response):
                        model_used = chunk.get("model") or model_used
                        text = _extract_delta_text(chunk)
                        if text:
                            collected_text.append(text)
                        if isinstance(chunk.get("usage"), dict):
                            usage_payload = chunk
                token_count = _tokens(usage_payload)
            else:
                data = await _post_completion(
                    client=client,
                    headers=headers,
                    payload=payload,
                    attempt=attempt,
                )
                collected_text = [_extract_text(data)]
                model_used = data.get("model") or model_used
                token_count = _tokens(data)
    except httpx.TimeoutException as exc:
        if not can_stream:
            raise _app_error(
                f"OpenRouter request timed out: {exc}",
                error_type="timeout_error",
                non_retryable=False,
                attempt=attempt,
            ) from exc
        raise _app_error(
            f"OpenRouter stream interrupted by timeout: {exc}",
            error_type="stream_interrupted_error",
            non_retryable=False,
            attempt=attempt,
        ) from exc
    except httpx.RequestError as exc:
        if not can_stream:
            raise _app_error(
                f"OpenRouter request failed: {exc}",
                error_type="network_error",
                non_retryable=False,
                attempt=attempt,
            ) from exc
        raise _app_error(
            f"OpenRouter stream interrupted by network error: {exc}",
            error_type="stream_interrupted_error",
            non_retryable=False,
            attempt=attempt,
        ) from exc

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    return {
        "response_text": "".join(collected_text),
        "model_used": model_used,
        "token_count": token_count,
        "latency_ms": latency_ms,
        "attempt": attempt,
        "was_streamed": can_stream,
    }
