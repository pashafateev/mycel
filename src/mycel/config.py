from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TelegramSettings:
    token: str
    allowed_users: list[int]


@dataclass
class TemporalSettings:
    address: str
    namespace: str
    task_queue: str


@dataclass
class WorkflowSettings:
    max_turns_before_continue_as_new: int = 8


@dataclass
class LLMSettings:
    default_role: str
    roles: dict[str, str]


@dataclass
class MycelSettings:
    telegram: TelegramSettings
    temporal: TemporalSettings
    workflow: WorkflowSettings
    llm: LLMSettings


def load_settings(path: str | Path) -> MycelSettings:
    raw = yaml.safe_load(Path(path).read_text())
    expanded = _expand_env(raw)
    return MycelSettings(
        telegram=TelegramSettings(**expanded["telegram"]),
        temporal=TemporalSettings(**expanded["temporal"]),
        workflow=WorkflowSettings(**expanded.get("workflow", {})),
        llm=LLMSettings(**expanded["llm"]),
    )


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str):
        return _expand_env_str(value)
    return value


def _expand_env_str(value: str) -> str:
    if value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value
