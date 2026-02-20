from __future__ import annotations

import argparse
import asyncio

from temporalio.client import Client

from tb09 import DEFAULT_DELIVERY_DB_PATH, DEFAULT_TASK_QUEUE
from tb09.scheduler import schedule_followups


async def _main(address: str, task_queue: str, db_path: str) -> None:
    client = await Client.connect(address)
    scheduled = await schedule_followups(
        client,
        task_queue=task_queue,
        db_path=db_path,
        delays=[30, 60, 90],
    )
    for item in scheduled:
        print(
            f"workflow_id={item['workflow_id']} reminder_id={item['reminder_id']} "
            f"delay={item['delay_seconds']} expected_at={item['expected_at']:.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Schedule TB9 follow-up reminders")
    parser.add_argument("--address", default="localhost:7233")
    parser.add_argument("--task-queue", default=DEFAULT_TASK_QUEUE)
    parser.add_argument("--db-path", default=DEFAULT_DELIVERY_DB_PATH)
    args = parser.parse_args()
    asyncio.run(_main(args.address, args.task_queue, args.db_path))


if __name__ == "__main__":
    main()
