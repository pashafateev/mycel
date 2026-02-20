from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    temporal_address: str = "localhost:7233"
    temporal_task_queue: str = "tb01-task-queue"
    workflow_id: str = "tb01-ping-workflow"


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    return Settings(
        telegram_bot_token=token,
        temporal_address=os.getenv("TEMPORAL_ADDRESS", "localhost:7233").strip()
        or "localhost:7233",
    )
