from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging

from mycel.bot import TelegramBotService
from mycel.config import load_settings
from mycel.temporal import connect_temporal
from mycel.worker import run_worker


async def run_app(config_path: str) -> None:
    settings = load_settings(config_path)
    temporal_client = await connect_temporal(settings.temporal)
    bot_service = TelegramBotService(settings, temporal_client)

    worker_task = asyncio.create_task(run_worker(config_path), name="mycel-worker")
    await bot_service.start()

    try:
        await asyncio.Event().wait()
    finally:
        await bot_service.stop()
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run Mycel bot + worker in one loop")
    parser.add_argument("--config", default="config/example.yaml")
    args = parser.parse_args()
    asyncio.run(run_app(args.config))


if __name__ == "__main__":
    main()
