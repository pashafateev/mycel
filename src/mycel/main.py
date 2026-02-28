from __future__ import annotations

import asyncio

from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker

from mycel.config import AppConfig
from mycel.telegram.bot import TelegramBotApp
from mycel.temporal.activities import generate_reply_activity
from mycel.temporal.workflows import ConversationWorkflow


async def run() -> None:
    config = AppConfig.from_env()
    temporal_client = await TemporalClient.connect(
        config.temporal.address,
        namespace=config.temporal.namespace,
    )

    bot = TelegramBotApp(config=config, temporal_client=temporal_client)
    async with Worker(
        temporal_client,
        task_queue=config.temporal.task_queue,
        workflows=[ConversationWorkflow],
        activities=[generate_reply_activity],
    ):
        await bot.run_forever()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
