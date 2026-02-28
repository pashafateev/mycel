from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from uuid import uuid4

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters
from temporalio.client import Client, WorkflowHandle
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

from tb01.workflows import PingWorkflow, pong_activity
from tb10.namespaces import parse_namespaced_command


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    temporal_address: str = "localhost:7233"
    temporal_task_queue: str = "tb10-mycel-task-queue"
    workflow_id: str = "tb10-mycel-ping-workflow"


@dataclass
class BotDeps:
    workflow_handle: WorkflowHandle


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN_MY", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN_MY is required")

    return Settings(
        telegram_bot_token=token,
        temporal_address=os.getenv("TEMPORAL_ADDRESS", "localhost:7233").strip()
        or "localhost:7233",
    )


async def ensure_ping_workflow(client: Client, workflow_id: str, task_queue: str) -> WorkflowHandle:
    try:
        await client.start_workflow(
            PingWorkflow.run,
            id=workflow_id,
            task_queue=task_queue,
        )
    except WorkflowAlreadyStartedError:
        pass

    return client.get_workflow_handle(workflow_id)


async def _wait_for_response(
    workflow_handle: WorkflowHandle,
    request_id: str,
    timeout_seconds: float = 10.0,
) -> str | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        response = await workflow_handle.query(PingWorkflow.get_response, request_id)
        if response is not None:
            return response
        await asyncio.sleep(0.2)
    return None


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    routed = parse_namespaced_command(update.message.text or "", namespace="m")
    if routed is None:
        return

    if routed.command == "help":
        await update.message.reply_text("[Mycel] Commands: /m_ping <text>, /m_help")
        return

    if routed.command != "ping":
        await update.message.reply_text(f"[Mycel] Unknown command: /m_{routed.command}")
        return

    deps: BotDeps = context.application.bot_data["deps"]
    message = routed.args or "hello"
    request_id = str(uuid4())
    await deps.workflow_handle.signal(
        PingWorkflow.enqueue_ping,
        {"request_id": request_id, "message": message},
    )

    response = await _wait_for_response(deps.workflow_handle, request_id)
    if response is None:
        await update.message.reply_text("[Mycel] Timed out waiting for workflow response.")
        return

    await update.message.reply_text(f"[Mycel] {response}")


def build_application(token: str, deps: BotDeps) -> Application:
    app = ApplicationBuilder().token(token).build()
    app.bot_data["deps"] = deps
    app.add_handler(MessageHandler(filters.TEXT, _handle_message))
    return app


async def run_worker(client: Client, task_queue: str, stop_event: asyncio.Event) -> None:
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[PingWorkflow],
        activities=[pong_activity],
    )
    async with worker:
        await stop_event.wait()


async def run_bot(token: str, deps: BotDeps, stop_event: asyncio.Event) -> None:
    app = build_application(token, deps)
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


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)


async def _main() -> None:
    settings = load_settings()
    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)

    client = await Client.connect(settings.temporal_address)
    workflow_handle = await ensure_ping_workflow(
        client=client,
        workflow_id=settings.workflow_id,
        task_queue=settings.temporal_task_queue,
    )

    worker_task = asyncio.create_task(
        run_worker(client, settings.temporal_task_queue, stop_event),
        name="tb10-mycel-worker",
    )
    bot_task = asyncio.create_task(
        run_bot(settings.telegram_bot_token, BotDeps(workflow_handle), stop_event),
        name="tb10-mycel-bot",
    )

    done, pending = await asyncio.wait({worker_task, bot_task}, return_when=asyncio.FIRST_EXCEPTION)
    for task in done:
        exc = task.exception()
        if exc is not None:
            stop_event.set()
            for pending_task in pending:
                pending_task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise exc

    stop_event.set()
    await asyncio.gather(*pending, return_exceptions=True)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
