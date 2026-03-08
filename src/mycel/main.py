from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker

from mycel.config import AppConfig
from mycel.lifecycle import SingletonPidFile, runtime_dir_from_env
from mycel.telegram.bot import TelegramBotApp
from mycel.temporal.activities import decide_next_step_activity, execute_tool_activity
from mycel.temporal.workflows import ConversationWorkflow


LOGGER = logging.getLogger(__name__)


async def run() -> None:
    config = AppConfig.from_env()
    runtime_dir = runtime_dir_from_env()

    with SingletonPidFile(runtime_dir, "mycel", "bot+worker"):
        LOGGER.info(
            "Starting Mycel with Temporal address=%s namespace=%s task_queue=%s",
            config.temporal.address,
            config.temporal.namespace,
            config.temporal.task_queue,
        )
        try:
            temporal_client = await TemporalClient.connect(
                config.temporal.address,
                namespace=config.temporal.namespace,
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to connect to Temporal at "
                f"{config.temporal.address} (namespace={config.temporal.namespace})"
            ) from exc

        bot = TelegramBotApp(config=config, temporal_client=temporal_client)
        try:
            async with Worker(
                temporal_client,
                task_queue=config.temporal.task_queue,
                workflows=[ConversationWorkflow],
                activities=[decide_next_step_activity, execute_tool_activity],
            ):
                await bot.run_forever()
        except Exception as exc:
            raise RuntimeError(
                "Mycel startup failed while initializing the Telegram poller or Temporal worker"
            ) from exc
        finally:
            LOGGER.info("Mycel shutdown complete")


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("MYCEL_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run())
    except Exception:
        LOGGER.exception("Fatal startup error")
        raise


if __name__ == "__main__":
    main()
