from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from temporalio.client import WorkflowHandle

from tb01.workflows import PingWorkflow


@dataclass
class UpdateTracker:
    seen_update_ids: set[int] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def register(self, update_id: int) -> bool:
        async with self.lock:
            if update_id in self.seen_update_ids:
                return False
            self.seen_update_ids.add(update_id)
            return True


@dataclass
class BotDeps:
    workflow_handle: WorkflowHandle
    tracker: UpdateTracker = field(default_factory=UpdateTracker)


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
    if not update.message:
        return

    deps: BotDeps = context.application.bot_data["deps"]
    envelope = await build_signal_envelope(
        deps=deps,
        update_id=update.update_id,
        chat_id=update.message.chat_id,
        sequence=update.message.message_id,
        message=message,
    )
    if envelope is None:
        return

    await deps.workflow_handle.signal(
        PingWorkflow.enqueue_ping,
        envelope,
    )

    response = await _wait_for_response(deps.workflow_handle, envelope["request_id"])
    if response is None:
        await update.message.reply_text("Timed out waiting for workflow response.")
        return

    await update.message.reply_text(response)


async def build_signal_envelope(
    deps: BotDeps,
    update_id: int,
    chat_id: int,
    sequence: int,
    message: str,
) -> Optional[dict[str, Any]]:
    is_new = await deps.tracker.register(update_id)
    if not is_new:
        return None
    return {
        "request_id": f"tg-{chat_id}-{update_id}-{uuid4().hex[:8]}",
        "update_id": update_id,
        "chat_id": chat_id,
        "sequence": sequence,
        "message": message,
    }


async def replay_update_payload(
    payload: dict[str, Any],
    deps: BotDeps,
) -> Optional[dict[str, Any]]:
    message = payload.get("message") or {}
    chat = message.get("chat") or {}
    if "update_id" not in payload or "id" not in chat:
        return None

    text = message.get("text") or "hello"
    if "message_id" not in message:
        return None
    return await build_signal_envelope(
        deps=deps,
        update_id=int(payload["update_id"]),
        chat_id=int(chat["id"]),
        sequence=int(message["message_id"]),
        message=str(text),
    )


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
