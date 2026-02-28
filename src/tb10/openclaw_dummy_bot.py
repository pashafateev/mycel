from __future__ import annotations

import asyncio
import os
import signal

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters

from tb10.namespaces import parse_namespaced_command


def load_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN_OC", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN_OC is required")
    return token


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not update.message:
        return

    routed = parse_namespaced_command(update.message.text or "", namespace="oc")
    if routed is None:
        return

    if routed.command == "help":
        await update.message.reply_text("[OpenClaw Dummy] Commands: /oc_ping <text>, /oc_help")
        return

    if routed.command == "ping":
        payload = routed.args or "hello"
        await update.message.reply_text(f"[OpenClaw Dummy] pong: {payload}")
        return

    await update.message.reply_text(f"[OpenClaw Dummy] Unknown command: /oc_{routed.command}")


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)


async def _main() -> None:
    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)

    app: Application = ApplicationBuilder().token(load_token()).build()
    app.add_handler(MessageHandler(filters.TEXT, _handle_message))

    await app.initialize()
    await app.start()
    if app.updater is None:
        raise RuntimeError("Telegram updater is not configured")
    await app.updater.start_polling(drop_pending_updates=True)

    try:
        await stop_event.wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
