from __future__ import annotations

import argparse
import asyncio
import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from mycel.config import MycelSettings, load_settings
from mycel.temporal import connect_temporal
from mycel.types import ConversationInput, MessageEnvelope
from mycel.workflows import ConversationWorkflow

LOGGER = logging.getLogger(__name__)


class TelegramBotService:
    def __init__(self, settings: MycelSettings, temporal_client: Client) -> None:
        self._settings = settings
        self._temporal_client = temporal_client
        self._app: Application = (
            ApplicationBuilder().token(self._settings.telegram.token).build()
        )
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))

    async def start(self) -> None:
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self) -> None:
        if self._app.updater:
            await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context

        if update.effective_user is None or update.message is None:
            return

        user_id = update.effective_user.id
        if self._settings.telegram.allowed_users and user_id not in self._settings.telegram.allowed_users:
            return

        text = update.message.text or ""
        request_id = f"{update.update_id}:{update.message.message_id}"
        workflow_id = f"conversation-{user_id}"
        envelope = MessageEnvelope(request_id=request_id, user_id=str(user_id), text=text)

        handle = self._temporal_client.get_workflow_handle(workflow_id)

        try:
            await self._temporal_client.start_workflow(
                ConversationWorkflow.run,
                ConversationInput(
                    user_id=str(user_id),
                    pending_messages=[envelope],
                    max_turns_before_continue_as_new=self._settings.workflow.max_turns_before_continue_as_new,
                ),
                id=workflow_id,
                task_queue=self._settings.temporal.task_queue,
            )
        except WorkflowAlreadyStartedError:
            await handle.signal(ConversationWorkflow.add_user_message, envelope)

        reply = await self._wait_for_reply(handle, request_id)
        await update.message.reply_text(reply)

    async def _wait_for_reply(self, handle, request_id: str, timeout_s: float = 10.0) -> str:
        poll_interval_s = 0.4
        checks = int(timeout_s / poll_interval_s)

        for _ in range(checks):
            response = await handle.query(ConversationWorkflow.get_response, request_id)
            if response:
                return response
            await asyncio.sleep(poll_interval_s)

        LOGGER.warning("Timed out waiting for reply for request_id=%s", request_id)
        return "Timed out waiting for workflow response. Please try again."


async def run_bot(config_path: str) -> None:
    settings = load_settings(config_path)
    temporal_client = await connect_temporal(settings.temporal)
    service = TelegramBotService(settings, temporal_client)

    await service.start()
    try:
        await asyncio.Event().wait()
    finally:
        await service.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run Mycel Telegram bot")
    parser.add_argument("--config", default="config/example.yaml")
    args = parser.parse_args()
    asyncio.run(run_bot(args.config))


if __name__ == "__main__":
    main()
