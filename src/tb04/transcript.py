from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_AFTER_REASONING = {"message", "function_call"}


def _assert_valid_item_shape(item: dict[str, Any], idx: int) -> None:
    item_type = item.get("type")
    if not isinstance(item_type, str) or not item_type:
        raise ValueError(f"Malformed transcript item at index {idx}: missing non-empty type")

    if item_type == "message":
        role = item.get("role")
        if not isinstance(role, str) or not role:
            raise ValueError(f"Malformed transcript message at index {idx}: missing role")
        content = item.get("content")
        if not isinstance(content, (str, list)):
            raise ValueError(
                f"Malformed transcript message at index {idx}: content must be str or list"
            )
        return

    if item_type == "function_call":
        name = item.get("name")
        arguments = item.get("arguments")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Malformed function_call at index {idx}: missing name")
        if not isinstance(arguments, (str, dict)):
            raise ValueError(
                f"Malformed function_call at index {idx}: arguments must be str or dict"
            )
        return

    if item_type == "reasoning":
        return

    raise ValueError(f"Malformed transcript item at index {idx}: unsupported type '{item_type}'")


def assert_no_orphan_reasoning(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop trailing orphan reasoning items and reject malformed in-list reasoning transitions."""
    if not items:
        return items

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Malformed transcript item at index {idx}: expected object")
        _assert_valid_item_shape(item, idx)

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
