from __future__ import annotations

from dataclasses import dataclass

import httpx

from mycel.config import OpenRouterConfig


class OpenRouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class OpenRouterClient:
    def __init__(self, config: OpenRouterConfig):
        self._config = config

    async def create_chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        stream: bool | None = None,
    ) -> str:
        if not messages:
            raise OpenRouterError("messages cannot be empty")

        use_model = model or self._config.model
        use_stream = self._config.streaming_enabled if stream is None else stream
        payload = {
            "model": use_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": use_stream,
        }

        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
            try:
                response = await client.post(
                    f"{self._config.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise OpenRouterError("OpenRouter response missing choices")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks = [part.get("text", "") for part in content if isinstance(part, dict)]
            return "".join(chunks).strip()

        raise OpenRouterError("OpenRouter response missing message content")
