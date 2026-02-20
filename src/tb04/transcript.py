from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_AFTER_REASONING = {"message", "function_call"}


def assert_no_orphan_reasoning(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop trailing orphan reasoning items and reject malformed in-list reasoning transitions."""
    if not items:
        return items

    orphan_start = len(items)
    for idx in range(len(items) - 1, -1, -1):
        if items[idx].get("type") == "reasoning":
            orphan_start = idx
            continue
        break

    if orphan_start < len(items):
        dropped = items[orphan_start:]
        logger.warning("Dropping %s orphan reasoning item(s) at transcript tail", len(dropped))
        items = items[:orphan_start]

    for idx, item in enumerate(items):
        if item.get("type") != "reasoning":
            continue
        if idx + 1 >= len(items):
            continue
        next_type = items[idx + 1].get("type")
        if next_type not in _ALLOWED_AFTER_REASONING:
            raise ValueError(
                "Malformed transcript: reasoning item must be followed by message or function_call"
            )

    return items


def validate_transcript(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and sanitize transcript items before LLM calls."""
    return assert_no_orphan_reasoning(items)
