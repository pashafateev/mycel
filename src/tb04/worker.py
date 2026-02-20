from __future__ import annotations

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import stream_llm
from .workflow import LLMStreamTestWorkflow

TASK_QUEUE = "tb04-streaming"


async def start_worker(client: Client, task_queue: str = TASK_QUEUE) -> Worker:
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[LLMStreamTestWorkflow],
        activities=[stream_llm],
    )
