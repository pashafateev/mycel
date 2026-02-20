from __future__ import annotations

import asyncio
import signal

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

from tb01.bot import BotDeps, build_application
from tb01.config import load_settings
from tb01.workflows import PingWorkflow, pong_activity


async def ensure_ping_workflow(
    client: Client,
    workflow_id: str,
    task_queue: str,
):
    try:
        await client.start_workflow(
            PingWorkflow.run,
            id=workflow_id,
            task_queue=task_queue,
        )
    except WorkflowAlreadyStartedError:
        pass

    return client.get_workflow_handle(workflow_id)


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
        client,
        workflow_id=settings.workflow_id,
        task_queue=settings.temporal_task_queue,
    )

    worker_task = asyncio.create_task(
        run_worker(client, settings.temporal_task_queue, stop_event),
        name="tb01-worker",
    )
    bot_task = asyncio.create_task(
        run_bot(settings.telegram_bot_token, BotDeps(workflow_handle), stop_event),
        name="tb01-bot",
    )

    done, pending = await asyncio.wait(
        {worker_task, bot_task},
        return_when=asyncio.FIRST_EXCEPTION,
    )

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
