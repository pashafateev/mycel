from __future__ import annotations

import argparse
import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from tb09 import DEFAULT_TASK_QUEUE
from tb09.workflows import FollowUpWorkflow, deliver_reminder


async def run_worker(address: str, task_queue: str) -> None:
    client = await Client.connect(address)
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[FollowUpWorkflow],
        activities=[deliver_reminder],
    )
    await worker.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TB9 Temporal worker")
    parser.add_argument("--address", default="localhost:7233")
    parser.add_argument("--task-queue", default=DEFAULT_TASK_QUEUE)
    args = parser.parse_args()
    asyncio.run(run_worker(args.address, args.task_queue))


if __name__ == "__main__":
    main()
