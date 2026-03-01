from pathlib import Path

from mycel.config import (
    AppConfig,
    OpenRouterConfig,
    PromptConfig,
    TelegramConfig,
    TemporalConfig,
)
from mycel.telegram.bot import format_status_block


def test_format_status_block_includes_required_fields_and_hides_secrets() -> None:
    config = AppConfig(
        telegram=TelegramConfig(bot_token="telegram-secret-token", allowed_user_id=42),
        temporal=TemporalConfig(
            address="localhost:7233",
            namespace="default",
            task_queue="mycel-phase1",
        ),
        openrouter=OpenRouterConfig(
            api_key="openrouter-secret-key",
            model="openai/gpt-5.2",
            streaming_enabled=True,
        ),
        prompt=PromptConfig(workspace_dir=Path("/tmp/workspace")),
    )

    status = format_status_block(config)

    assert "model: openai/gpt-5.2" in status
    assert "temporal: address=localhost:7233 namespace=default task_queue=mycel-phase1" in status
    assert "streaming_enabled: true" in status
    assert "workspace_dir: /tmp/workspace" in status
    assert "allowed_user_id: 42" in status
    assert "python_version: " in status
    assert "mycel_version: " in status
    assert "telegram-secret-token" not in status
    assert "openrouter-secret-key" not in status
