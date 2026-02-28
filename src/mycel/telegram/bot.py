from __future__ import annotations

import asyncio
import signal
import uuid
from datetime import timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from temporalio.client import Client as TemporalClient

from mycel.config import AppConfig
from mycel.temporal.types import ConversationReply, ConversationRequest
from mycel.temporal.workflows import ConversationWorkflow
from mycel.utils.namespaces import is_mycel_command, parse_namespaced_command


class TelegramBotApp:
    def __init__(self, config: AppConfig, temporal_client: TemporalClient):
        self._config = config
        self._temporal_client = temporal_client
        self._app = Application.builder().token(config.telegram.bot_token).build()
        self._stop_event = asyncio.Event()

        self._app.add_handler(CommandHandler("m_help", self._on_m_help))
        self._app.add_handler(CommandHandler("m_whoami", self._on_m_whoami))
        self._app.add_handler(CommandHandler("m_chat", self._on_m_chat))

    async def run_forever(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop_event.set)
            except NotImplementedError:
                pass

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        try:
            await self._stop_event.wait()
        finally:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def _on_m_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed_user(update):
            return
        await update.effective_message.reply_text(
            "Commands:\n"
            "/m_help - show this message\n"
            "/m_whoami - show your Telegram user id and username\n"
            "/m_chat <text> - send one chat turn through Temporal + OpenRouter"
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

        workflow_id = f"mycel-{update.effective_user.id}-{uuid.uuid4().hex[:8]}"
        reply = await self._temporal_client.execute_workflow(
            ConversationWorkflow.run,
            ConversationRequest(user_id=update.effective_user.id, text=parsed.args),
            id=workflow_id,
            task_queue=self._config.temporal.task_queue,
            run_timeout=timedelta(seconds=120),
            result_type=ConversationReply,
        )
        await update.effective_message.reply_text(reply.text)

    def _is_allowed_user(self, update: Update) -> bool:
        user = update.effective_user
        if user is None:
            return False
        return user.id == self._config.telegram.allowed_user_id

    @staticmethod
    def should_process_message(text: str) -> bool:
        return is_mycel_command(text)
