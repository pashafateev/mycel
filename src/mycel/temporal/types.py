from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationRequest:
    user_id: int
    text: str


@dataclass
class ConversationReply:
    text: str


@dataclass
class ConversationMessage:
    role: str
    content: str


@dataclass
class LLMTurnRequest:
    messages: list[ConversationMessage]


@dataclass
class LLMTurnResponse:
    type: str
    text: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidatedToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolExecutionRequest:
    tool: ValidatedToolCall
