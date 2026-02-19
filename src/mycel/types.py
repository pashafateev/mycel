from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MessageEnvelope:
    request_id: str
    user_id: str
    text: str


@dataclass
class ConversationTurn:
    role: str
    text: str
    request_id: str


@dataclass
class ConversationInput:
    user_id: str
    pending_messages: list[MessageEnvelope] = field(default_factory=list)
    history: list[ConversationTurn] = field(default_factory=list)
    turn_count: int = 0
    max_turns_before_continue_as_new: int = 8


@dataclass
class LLMRequest:
    request_id: str
    user_id: str
    model_role: str
    model_name: str
    history: list[dict[str, Any]]
    user_message: str
    tool_result: str | None = None


@dataclass
class LLMResponse:
    reply: str
    model_role: str
    model_name: str


@dataclass
class MemoryUpdateRequest:
    user_id: str
    request_id: str
    latest_user_message: str
    latest_assistant_message: str


@dataclass
class ToolExecRequest:
    request_id: str
    tool_name: str
    payload: dict[str, Any]
