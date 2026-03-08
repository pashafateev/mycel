from __future__ import annotations

import asyncio

from temporalio import activity

from mycel.config import AppConfig
from mycel.llm.openrouter import ChatMessage, OpenRouterClient
from mycel.prompt.system_prompt import build_system_prompt
from mycel.temporal.types import LLMTurnRequest, LLMTurnResponse, ToolExecutionRequest
from mycel.tools.m_fetch import fetch_url_summary
from mycel.tools.m_file import read_file, write_file
from mycel.tools.m_note import append_note
from mycel.tools.registry import parse_llm_turn_response, render_tool_instructions


@activity.defn
async def decide_next_step_activity(request: LLMTurnRequest) -> LLMTurnResponse:
    config = AppConfig.from_env()
    client = OpenRouterClient(config.openrouter)
    system_prompt = (
        f"{build_system_prompt(config.prompt.workspace_dir)}\n\n"
        f"{render_tool_instructions()}"
    )

    llm_messages = [
        ChatMessage(role="system", content=system_prompt),
    ]
    llm_messages.extend(_render_llm_messages(request))

    raw = await client.create_chat_completion(messages=llm_messages)
    try:
        return parse_llm_turn_response(raw)
    except ValueError:
        return LLMTurnResponse(
            type="final",
            text="I couldn't produce a valid structured response for this turn.",
        )


@activity.defn
async def execute_tool_activity(request: ToolExecutionRequest) -> str:
    config = AppConfig.from_env()
    tool = request.tool

    try:
        if tool.name == "web_fetch":
            return await asyncio.to_thread(fetch_url_summary, tool.arguments["url"])
        if tool.name == "read_file":
            return await asyncio.to_thread(
                read_file,
                config.prompt.workspace_dir,
                tool.arguments["path"],
            )
        if tool.name == "write_file":
            written_path = await asyncio.to_thread(
                write_file,
                config.prompt.workspace_dir,
                tool.arguments["path"],
                tool.arguments["content"],
            )
            relative_written = written_path.relative_to(config.prompt.workspace_dir.resolve())
            return f"Wrote {relative_written.as_posix()}"
        if tool.name == "memory_note":
            note_path = await asyncio.to_thread(
                append_note,
                config.prompt.workspace_dir,
                tool.arguments["text"],
            )
            return f"Saved note to memory/{note_path.name}"
    except (RuntimeError, ValueError) as exc:
        return f"Tool error: {exc}"

    return f"Tool error: unsupported tool {tool.name}"


def _render_llm_messages(request: LLMTurnRequest) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for message in request.messages:
        if message.role == "tool":
            messages.append(
                ChatMessage(
                    role="user",
                    content=f"Tool result:\n{message.content}",
                )
            )
            continue

        role = message.role if message.role in {"user", "assistant"} else "user"
        messages.append(ChatMessage(role=role, content=message.content))
    return messages
