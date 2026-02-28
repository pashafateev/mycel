from __future__ import annotations

from temporalio import activity

from mycel.config import AppConfig
from mycel.llm.openrouter import ChatMessage, OpenRouterClient
from mycel.prompt.system_prompt import build_system_prompt
from mycel.temporal.types import ConversationRequest


@activity.defn
async def generate_reply_activity(request: ConversationRequest) -> str:
    config = AppConfig.from_env()
    client = OpenRouterClient(config.openrouter)
    system_prompt = build_system_prompt(config.prompt.workspace_dir)

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=request.text),
    ]

    return await client.create_chat_completion(messages=messages)
