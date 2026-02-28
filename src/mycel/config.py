from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    allowed_user_id: int


@dataclass(frozen=True)
class TemporalConfig:
    address: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "mycel-phase1"


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str = "openai/gpt-5.2"
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 60.0
    streaming_enabled: bool = False


@dataclass(frozen=True)
class PromptConfig:
    workspace_dir: Path


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    temporal: TemporalConfig
    openrouter: OpenRouterConfig
    prompt: PromptConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        bot_token = _must_get_env("TELEGRAM_BOT_TOKEN")
        allowed_user_id = int(_must_get_env("MYCEL_ALLOWED_USER_ID"))
        openrouter_key = _must_get_env("OPENROUTER_API_KEY")

        temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
        temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
        temporal_task_queue = os.getenv("MYCEL_TASK_QUEUE", "mycel-phase1")

        model = os.getenv("MYCEL_MODEL", "openai/gpt-5.2")
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        timeout_seconds = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60"))
        streaming_enabled = _to_bool(os.getenv("MYCEL_STREAMING_ENABLED", "0"))

        workspace_dir = Path(os.getenv("MYCEL_WORKSPACE_DIR", Path.cwd()))

        return cls(
            telegram=TelegramConfig(bot_token=bot_token, allowed_user_id=allowed_user_id),
            temporal=TemporalConfig(
                address=temporal_address,
                namespace=temporal_namespace,
                task_queue=temporal_task_queue,
            ),
            openrouter=OpenRouterConfig(
                api_key=openrouter_key,
                model=model,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                streaming_enabled=streaming_enabled,
            ),
            prompt=PromptConfig(workspace_dir=workspace_dir),
        )


def _must_get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
