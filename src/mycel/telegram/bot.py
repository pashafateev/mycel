from __future__ import annotations

import asyncio
import logging
import platform
import signal
import time
import uuid
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Callable

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from temporalio.client import Client as TemporalClient

from mycel.config import AppConfig
from mycel.lifecycle import temporal_is_reachable
from mycel.temporal.types import ConversationReply, ConversationRequest
from mycel.temporal.workflows import ConversationWorkflow
from mycel.tools.m_fetch import fetch_url_summary
from mycel.tools.m_file import read_file, write_file
from mycel.tools.m_note import append_note
from mycel.utils.namespaces import is_mycel_command, parse_namespaced_command


LOGGER = logging.getLogger(__name__)


def _get_mycel_version() -> str:
    try:
        return version("mycel")
    except PackageNotFoundError:
        return "unknown"


def format_status_block(config: AppConfig) -> str:
    python_version = platform.python_version()
    mycel_version = _get_mycel_version()
    lines = [
        "status:",
        f"model: {config.openrouter.model}",
        (
            "temporal: "
            f"address={config.temporal.address} "
            f"namespace={config.temporal.namespace} "
            f"task_queue={config.temporal.task_queue}"
        ),
        f"streaming_enabled: {str(config.openrouter.streaming_enabled).lower()}",
        f"workspace_dir: {config.prompt.workspace_dir}",
        f"allowed_user_id: {config.telegram.allowed_user_id}",
        f"python_version: {python_version}",
        f"mycel_version: {mycel_version}",
    ]
    return "\n".join(lines)


def format_health_status(
    *,
    telegram_connected: bool | None,
    temporal_reachable: bool,
    worker_running: bool,
    task_queue: str,
    namespace: str,
    uptime_seconds: float,
) -> str:
    telegram_status = "connected" if telegram_connected else "unknown"
    temporal_status = "reachable" if temporal_reachable else "unreachable"
    worker_status = "running" if worker_running else "stopped"
    uptime = format_uptime_seconds(uptime_seconds)
    return (
        f"telegram: {telegram_status}\n"
        f"temporal: {temporal_status}\n"
        f"worker: {worker_status}\n"
        f"task_queue: {task_queue}\n"
        f"namespace: {namespace}\n"
        f"uptime: {uptime}"
    )


def format_uptime_seconds(uptime_seconds: float) -> str:
    total_seconds = max(0, int(uptime_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def build_health_status(
    config: AppConfig,
    *,
    started_at_monotonic: float,
    now_monotonic: float | None = None,
    telegram_connected: bool | None = True,
    worker_running: bool = True,
    temporal_check: Callable[[str], bool] | None = None,
) -> str:
    now = time.monotonic() if now_monotonic is None else now_monotonic
    checker = temporal_is_reachable if temporal_check is None else temporal_check
    try:
        temporal_reachable = bool(checker(config.temporal.address))
    except Exception:
        temporal_reachable = False

    return format_health_status(
        telegram_connected=telegram_connected,
        temporal_reachable=temporal_reachable,
        worker_running=worker_running,
        task_queue=config.temporal.task_queue,
        namespace=config.temporal.namespace,
        uptime_seconds=now - started_at_monotonic,
    )


class TelegramBotApp:
    def __init__(self, config: AppConfig, temporal_client: TemporalClient):
        self._config = config
        self._temporal_client = temporal_client
        self._app = Application.builder().token(config.telegram.bot_token).build()
        self._stop_event = asyncio.Event()
        self._started_at_monotonic = time.monotonic()

        self._app.add_handler(CommandHandler("m_help", self._on_m_help))
        self._app.add_handler(CommandHandler("m_health", self._on_m_health))
        self._app.add_handler(CommandHandler("m_whoami", self._on_m_whoami))
        self._app.add_handler(CommandHandler("m_status", self._on_m_status))
        self._app.add_handler(CommandHandler("m_chat", self._on_m_chat))
        self._app.add_handler(CommandHandler("m_fetch", self._on_m_fetch))
        self._app.add_handler(CommandHandler("m_note", self._on_m_note))
        self._app.add_handler(CommandHandler("m_read", self._on_m_read))
        self._app.add_handler(CommandHandler("m_write", self._on_m_write))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_natural_language))

    async def run_forever(self) -> None:
        loop = asyncio.get_running_loop()
        initialized = False
        started = False
        polling_started = False
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop_event.set)
            except NotImplementedError:
                pass

        LOGGER.info("Initializing Telegram application")
        try:
            await self._app.initialize()
            initialized = True
            await self._app.start()
            started = True
            if self._app.updater is None:
                raise RuntimeError("Telegram updater is unavailable")
            await self._app.updater.start_polling(drop_pending_updates=True)
            polling_started = True
        except Exception as exc:
            await self._shutdown(initialized=initialized, started=started, polling_started=polling_started)
            raise RuntimeError("Failed to start Telegram polling") from exc

        try:
            LOGGER.info("Telegram polling started")
            await self._stop_event.wait()
        finally:
            LOGGER.info("Stopping Telegram application")
            await self._shutdown(initialized=initialized, started=started, polling_started=polling_started)

    async def _shutdown(self, *, initialized: bool, started: bool, polling_started: bool) -> None:
        if polling_started and self._app.updater is not None:
            await self._app.updater.stop()
        if started:
            await self._app.stop()
        if initialized:
            await self._app.shutdown()

    async def _on_m_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        await update.effective_message.reply_text(
            "Commands:\n"
            "Natural language mode: plain text messages route through the Temporal chat workflow.\n"
            "/m_help - show this message\n"
            "/m_health - show compact health status\n"
            "/m_whoami - show your Telegram user id and username\n"
            "/m_status - show current runtime status\n"
            "/m_chat <text> - send one chat turn through Temporal + OpenRouter\n"
            "/m_fetch <url> - fetch a URL and return a short summary\n"
            "/m_note <text> - append a bullet to today's memory note\n"
            "/m_read <relative-path> - read a workspace file (truncated)\n"
            "/m_write <relative-path> <content> - overwrite a workspace file"
        )

    async def _on_m_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        message = update.effective_message
        if user is None or message is None:
            return

        lines = [f"user_id: {user.id}"]
        if user.username:
            lines.append(f"username: @{user.username}")
        else:
            lines.append("username: <not set>")
        await message.reply_text("\n".join(lines))

    async def _on_m_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        message = update.effective_message
        if message is None:
            return
        await message.reply_text(format_status_block(self._config))

    async def _on_m_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        message = update.effective_message
        if message is None:
            return
        await message.reply_text(
            build_health_status(
                self._config,
                started_at_monotonic=self._started_at_monotonic,
                telegram_connected=True,
                worker_running=True,
            )
        )

    async def _on_m_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        text = update.effective_message.text if update.effective_message else ""
        parsed = parse_namespaced_command(text or "")
        if parsed is None or parsed.namespace != "m" or parsed.command != "chat":
            return
        if not parsed.args:
            await update.effective_message.reply_text("Usage: /m_chat <text>")
            return

        await self._reply_with_workflow_result(update, parsed.args)

    async def _on_natural_language(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        text = update.effective_message.text if update.effective_message else ""
        if not text.strip():
            return
        LOGGER.info("Natural language handler fired for user_id=%s text=%r", update.effective_user.id, text)
        await self._reply_with_workflow_result(update, text)

    async def _reply_with_workflow_result(self, update: Update, text: str) -> None:
        if update.effective_user is None or update.effective_message is None:
            return

        workflow_id = f"mycel-{update.effective_user.id}-{uuid.uuid4().hex[:8]}"
        LOGGER.info("Dispatching ConversationWorkflow for user_id=%s workflow_id=%s", update.effective_user.id, workflow_id)
        reply = await self._temporal_client.execute_workflow(
            ConversationWorkflow.run,
            ConversationRequest(user_id=update.effective_user.id, text=text),
            id=workflow_id,
            task_queue=self._config.temporal.task_queue,
            run_timeout=timedelta(seconds=120),
            result_type=ConversationReply,
        )
        await update.effective_message.reply_text(reply.text)

    async def _on_m_fetch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        text = update.effective_message.text if update.effective_message else ""
        parsed = parse_namespaced_command(text or "")
        if parsed is None or parsed.namespace != "m" or parsed.command != "fetch":
            return
        if not parsed.args:
            await update.effective_message.reply_text("Usage: /m_fetch <http(s)://url>")
            return

        try:
            summary = await asyncio.to_thread(fetch_url_summary, parsed.args)
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return
        except RuntimeError as exc:
            await update.effective_message.reply_text(str(exc))
            return

        await update.effective_message.reply_text(summary)

    async def _on_m_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        text = update.effective_message.text if update.effective_message else ""
        parsed = parse_namespaced_command(text or "")
        if parsed is None or parsed.namespace != "m" or parsed.command != "note":
            return
        if not parsed.args:
            await update.effective_message.reply_text("Usage: /m_note <text>")
            return

        try:
            note_path = await asyncio.to_thread(
                append_note,
                self._config.prompt.workspace_dir,
                parsed.args,
            )
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return

        await update.effective_message.reply_text(f"Saved note to memory/{note_path.name}")

    async def _on_m_read(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        text = update.effective_message.text if update.effective_message else ""
        parsed = parse_namespaced_command(text or "")
        if parsed is None or parsed.namespace != "m" or parsed.command != "read":
            return
        if not parsed.args:
            await update.effective_message.reply_text("Usage: /m_read <relative-path>")
            return

        try:
            content = await asyncio.to_thread(
                read_file,
                self._config.prompt.workspace_dir,
                parsed.args,
            )
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return

        await update.effective_message.reply_text(content)

    async def _on_m_write(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        text = update.effective_message.text if update.effective_message else ""
        parsed = parse_namespaced_command(text or "")
        if parsed is None or parsed.namespace != "m" or parsed.command != "write":
            return
        if not parsed.args:
            await update.effective_message.reply_text("Usage: /m_write <relative-path> <content>")
            return

        parts = parsed.args.split(maxsplit=1)
        if len(parts) != 2:
            await update.effective_message.reply_text("Usage: /m_write <relative-path> <content>")
            return
        relative_path, content = parts
        if not content:
            await update.effective_message.reply_text("Usage: /m_write <relative-path> <content>")
            return

        try:
            written_path = await asyncio.to_thread(
                write_file,
                self._config.prompt.workspace_dir,
                relative_path,
                content,
            )
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return

        relative_written = written_path.relative_to(self._config.prompt.workspace_dir.resolve())
        await update.effective_message.reply_text(f"Wrote {relative_written.as_posix()}")

    def _is_allowed_user(self, update: Update) -> bool:
        user = update.effective_user
        if user is None:
            return False
        return user.id == self._config.telegram.allowed_user_id

    @staticmethod
    def should_process_message(text: str) -> bool:
        stripped = text.strip()
        return bool(stripped) and (not stripped.startswith("/") or is_mycel_command(stripped))
