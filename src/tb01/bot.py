from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from temporalio.client import WorkflowHandle

from tb01.workflows import PingWorkflow


@dataclass
class BotDeps:
    workflow_handle: WorkflowHandle


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message:
        await update.message.reply_text("Welcome to TB1. Send /ping <message> or any text.")


async def _ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    text = update.message.text or ""
    message = text.replace("/ping", "", 1).strip() or "hello"
    await _send_ping(update, context, message)


async def _text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    await _send_ping(update, context, update.message.text or "hello")


async def _send_ping(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    deps: BotDeps = context.application.bot_data["deps"]
    request_id = str(uuid4())

    await deps.workflow_handle.signal(
        PingWorkflow.enqueue_ping,
        {"request_id": request_id, "message": message},
    )

    response = await _wait_for_response(deps.workflow_handle, request_id)
    if response is None:
        await update.message.reply_text("Timed out waiting for workflow response.")
        return

    await update.message.reply_text(response)


async def _wait_for_response(
    workflow_handle: WorkflowHandle,
    request_id: str,
    timeout_seconds: float = 10.0,
) -> Optional[str]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        response = await workflow_handle.query(PingWorkflow.get_response, request_id)
        if response is not None:
            return response
        await asyncio.sleep(0.2)
    return None


def build_application(token: str, deps: BotDeps) -> Application:
    app = ApplicationBuilder().token(token).build()
    app.bot_data["deps"] = deps
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("ping", _ping))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _text))
    return app
