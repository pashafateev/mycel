from __future__ import annotations

import argparse
import asyncio

from temporalio.worker import Worker

from mycel.activities import mock_llm_call, mock_memory_update, mock_tool_exec
from mycel.config import load_settings
from mycel.temporal import connect_temporal
from mycel.workflows import ConversationWorkflow


async def run_worker(config_path: str) -> None:
    settings = load_settings(config_path)
    client = await connect_temporal(settings.temporal)

    worker = Worker(
        client,
        task_queue=settings.temporal.task_queue,
        workflows=[ConversationWorkflow],
        activities=[mock_llm_call, mock_memory_update, mock_tool_exec],
    )
    await worker.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Mycel Temporal worker")
    parser.add_argument("--config", default="config/example.yaml")
    args = parser.parse_args()
    asyncio.run(run_worker(args.config))


if __name__ == "__main__":
    main()
