from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConversationRequest:
    user_id: int
    text: str


@dataclass
class ConversationReply:
    text: str
