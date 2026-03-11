import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mycel.config import AppConfig, OpenRouterConfig, PromptConfig, TelegramConfig, TemporalConfig
from mycel.temporal.types import ConversationReply, ConversationRequest
from mycel.utils.namespaces import is_mycel_command, parse_namespaced_command
from mycel.telegram.bot import TelegramBotApp


def test_parse_simple_command() -> None:
    parsed = parse_namespaced_command("/m_chat hello world")
    assert parsed is not None
    assert parsed.namespace == "m"
    assert parsed.command == "chat"
    assert parsed.args == "hello world"


def test_parse_command_with_bot_suffix() -> None:
    parsed = parse_namespaced_command("/m_help@mybot")
    assert parsed is not None
    assert parsed.namespace == "m"
    assert parsed.command == "help"
    assert parsed.args == ""


def test_parse_non_namespaced_command_returns_none() -> None:
    assert parse_namespaced_command("/start") is None
    assert parse_namespaced_command("hello") is None


def test_is_mycel_command() -> None:
    assert is_mycel_command("/m_help") is True
    assert is_mycel_command("/m_chat test") is True
    assert is_mycel_command("/x_help") is False


def test_should_process_message_supports_hybrid_mode() -> None:
    assert TelegramBotApp.should_process_message("hello") is True
    assert TelegramBotApp.should_process_message("summarize https://example.com") is True
    assert TelegramBotApp.should_process_message("/m_chat hello") is True
    assert TelegramBotApp.should_process_message("/start") is False


def test_on_natural_language_routes_raw_text_through_conversation_workflow(caplog) -> None:
    bot = TelegramBotApp.__new__(TelegramBotApp)
    bot._config = AppConfig(
        telegram=TelegramConfig(bot_token="telegram-secret-token", allowed_user_id=42),
        temporal=TemporalConfig(task_queue="mycel-phase1"),
        openrouter=OpenRouterConfig(api_key="openrouter-secret-key"),
        prompt=PromptConfig(workspace_dir=Path("/tmp/workspace")),
    )
    bot._temporal_client = SimpleNamespace(
        execute_workflow=AsyncMock(return_value=ConversationReply(text="summary"))
    )

    message = SimpleNamespace(
        text="summarize https://example.com",
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=message,
    )

    with caplog.at_level("INFO"):
        asyncio.run(bot._on_natural_language(update, None))

    bot._temporal_client.execute_workflow.assert_awaited_once()
    workflow_call = bot._temporal_client.execute_workflow.await_args
    assert workflow_call.args[1] == ConversationRequest(
        user_id=42,
        text="summarize https://example.com",
    )
    message.reply_text.assert_awaited_once_with("summary")
    assert "Natural language handler fired" in caplog.text
