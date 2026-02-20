from __future__ import annotations

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import call_llm
from .workflow import LLMTestWorkflow

TASK_QUEUE = "tb03-openrouter"


async def start_worker(client: Client, task_queue: str = TASK_QUEUE) -> Worker:
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[LLMTestWorkflow],
        activities=[call_llm],
    )
