from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class MessageEvent:
    text: str
    chat_id: int
    chat_type: str = "private"
    sent_at: Optional[datetime] = None


class FirstResponderState:
    """Shared state file used by bots to claim shared commands once."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def claim(self, command: str, bot_name: str) -> bool:
        state = self._read_state()
        claims = state.setdefault("claims", {})
        if command in claims:
            return False

        claims[command] = {
            "bot": bot_name,
            "claimed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        self._write_state(state)
        return True

    def _read_state(self) -> dict:
        if not self._path.exists():
            return {"claims": {}}
        raw = self._path.read_text(encoding="utf-8").strip()
        if not raw:
            return {"claims": {}}
        return json.loads(raw)

    def _write_state(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


class MycelBot:
    name = "mycel"

    def __init__(self, shared_state_path: Path) -> None:
        self._shared_state = FirstResponderState(shared_state_path)

    def handle(self, event: MessageEvent) -> Optional[str]:
        command = _extract_command(event.text)

        if command:
            if command.startswith("/oc_"):
                return None
            if command == "/m_ping":
                return "Mycel pong"
            if command == "/m_remind":
                reminder = _command_argument(event.text) or "(empty reminder)"
                return f"Mycel reminder scheduled: {reminder}"
            if command == "/m_status":
                return "Mycel status: healthy"
            if command in {"/start", "/help"}:
                if self._shared_state.claim(command, self.name):
                    return f"Mycel handled {command}"
                return None
            return None

        plain_text = (event.text or "").strip()
        if plain_text:
            return f"Mycel default reply: {plain_text}"
        return None


class OpenClawBotSimulator:
    name = "openclaw"

    def handle(self, event: MessageEvent) -> Optional[str]:
        command = _extract_command(event.text)
        if not command:
            return None

        if command.startswith("/m_"):
            return None
        if command == "/oc_ping":
            return "OpenClaw pong"
        if command == "/oc_status":
            return "OpenClaw status: healthy"
        return None


def _extract_command(text: str) -> Optional[str]:
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None

    first_token = raw.split(" ", 1)[0]
    command = first_token.split("@", 1)[0]
    return command


def _command_argument(text: str) -> str:
    tokens = (text or "").strip().split(" ", 1)
    if len(tokens) < 2:
        return ""
    return tokens[1].strip()
