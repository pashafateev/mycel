from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from mycel.temporal.types import LLMTurnResponse, ValidatedToolCall

MAX_TOOL_DEPTH = 5


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    required_args: tuple[str, ...]


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "web_fetch": ToolSpec(
        name="web_fetch",
        description="Fetch a URL and return a short readable summary.",
        required_args=("url",),
    ),
    "read_file": ToolSpec(
        name="read_file",
        description="Read a workspace-relative file and return truncated text.",
        required_args=("path",),
    ),
    "write_file": ToolSpec(
        name="write_file",
        description="Overwrite a workspace-relative file with provided content.",
        required_args=("path", "content"),
    ),
    "memory_note": ToolSpec(
        name="memory_note",
        description="Append a short note to today's memory note file.",
        required_args=("text",),
    ),
}


def render_tool_instructions() -> str:
    tool_lines = []
    for spec in TOOL_REGISTRY.values():
        args = ", ".join(spec.required_args)
        tool_lines.append(f"- {spec.name}({args}): {spec.description}")

    return (
        "You must return valid JSON only.\n"
        'Reply with {"type":"final","text":"..."} when no tool is needed.\n'
        'Reply with {"type":"tool_call","tool_name":"...","arguments":{...}} when exactly one tool call is needed.\n'
        "Do not return arrays. Do not return more than one tool call.\n"
        "Available tools:\n"
        f"{chr(10).join(tool_lines)}"
    )


def parse_llm_turn_response(raw: str) -> LLMTurnResponse:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response was not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object.")

    response_type = payload.get("type")
    if response_type == "final":
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Final response must include non-empty text.")
        return LLMTurnResponse(type="final", text=text.strip())

    if response_type == "tool_call":
        tool_name = payload.get("tool_name")
        arguments = payload.get("arguments")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("Tool call must include tool_name.")
        if not isinstance(arguments, dict):
            raise ValueError("Tool call must include arguments object.")
        return LLMTurnResponse(
            type="tool_call",
            tool_name=tool_name.strip(),
            arguments=arguments,
        )

    raise ValueError("LLM response type must be final or tool_call.")


def validate_tool_call(response: LLMTurnResponse) -> ValidatedToolCall:
    if response.type != "tool_call" or not response.tool_name:
        raise ValueError("Expected a tool_call response.")

    spec = TOOL_REGISTRY.get(response.tool_name)
    if spec is None:
        raise ValueError(f"Unknown tool: {response.tool_name}")

    provided_keys = set(response.arguments.keys())
    required_keys = set(spec.required_args)
    if provided_keys != required_keys:
        raise ValueError(
            f"Invalid arguments for {spec.name}. Expected keys: {', '.join(spec.required_args)}"
        )

    validators = {
        "web_fetch": _validate_web_fetch_args,
        "read_file": _validate_read_file_args,
        "write_file": _validate_write_file_args,
        "memory_note": _validate_memory_note_args,
    }
    return ValidatedToolCall(name=spec.name, arguments=validators[spec.name](response.arguments))


def _validate_web_fetch_args(arguments: dict[str, Any]) -> dict[str, str]:
    url = arguments.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("web_fetch.url must be a non-empty string.")
    return {"url": url.strip()}


def _validate_read_file_args(arguments: dict[str, Any]) -> dict[str, str]:
    return {"path": _validate_workspace_path(arguments.get("path"), field_name="path")}


def _validate_write_file_args(arguments: dict[str, Any]) -> dict[str, str]:
    path = _validate_workspace_path(arguments.get("path"), field_name="path")
    content = arguments.get("content")
    if not isinstance(content, str) or not content:
        raise ValueError("write_file.content must be a non-empty string.")
    return {"path": path, "content": content}


def _validate_memory_note_args(arguments: dict[str, Any]) -> dict[str, str]:
    text = arguments.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("memory_note.text must be a non-empty string.")
    return {"text": text.strip()}


def _validate_workspace_path(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")

    raw = value.strip()
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise ValueError(f"{field_name} must be relative to the workspace.")
    if any(part in {"..", ""} for part in path.parts):
        raise ValueError(f"{field_name} must stay within the workspace.")

    return raw
