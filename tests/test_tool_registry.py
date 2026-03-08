from __future__ import annotations

import pytest

from mycel.temporal.types import LLMTurnResponse
from mycel.tools.registry import parse_llm_turn_response, validate_tool_call


def test_parse_llm_turn_response_reads_tool_call() -> None:
    response = parse_llm_turn_response(
        '{"type":"tool_call","tool_name":"read_file","arguments":{"path":"notes/today.md"}}'
    )

    assert response.type == "tool_call"
    assert response.tool_name == "read_file"
    assert response.arguments == {"path": "notes/today.md"}


def test_validate_tool_call_rejects_unknown_tool() -> None:
    response = LLMTurnResponse(
        type="tool_call",
        tool_name="shell_exec",
        arguments={"cmd": "rm -rf /"},
    )

    with pytest.raises(ValueError, match="Unknown tool"):
        validate_tool_call(response)


def test_validate_tool_call_rejects_workspace_escape() -> None:
    response = LLMTurnResponse(
        type="tool_call",
        tool_name="read_file",
        arguments={"path": "../secret.txt"},
    )

    with pytest.raises(ValueError, match="within the workspace"):
        validate_tool_call(response)
