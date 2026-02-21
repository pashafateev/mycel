#!/usr/bin/env python3
from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from tb10.router import MessageEvent, MycelBot, OpenClawBotSimulator


def build_command_set() -> list[str]:
    commands = []
    commands.extend(["/m_ping"] * 5)
    commands.extend(["/oc_ping"] * 5)
    commands.extend(["/m_remind test"] * 3)
    commands.extend(["/oc_status"] * 3)
    commands.extend(["hello"] * 2)
    commands.append("/start")
    commands.append("/help")
    if len(commands) != 20:
        raise AssertionError("Expected exactly 20 commands")
    return commands


def expected_owner(command_text: str) -> str:
    if command_text.startswith("/m_ping"):
        return "mycel"
    if command_text.startswith("/m_remind"):
        return "mycel"
    if command_text.startswith("/m_status"):
        return "mycel"
    if command_text.startswith("/oc_ping"):
        return "openclaw"
    if command_text.startswith("/oc_status"):
        return "openclaw"
    if command_text in {"/start", "/help"}:
        return "shared-single"
    if not command_text.startswith("/"):
        return "mycel"
    return "none"


def run_simulation() -> None:
    with TemporaryDirectory(prefix="tb10-state-") as tmpdir:
        state_path = Path(tmpdir) / "first_responder_state.json"
        mycel = MycelBot(state_path)
        openclaw = OpenClawBotSimulator()

        commands = build_command_set()
        random.Random(10).shuffle(commands)

        start_at = datetime(2026, 2, 21, 12, 0, 0)
        step_seconds = 90  # 20 events over 30 minutes

        double_handled = 0
        for idx, text in enumerate(commands):
            event = MessageEvent(
                text=text,
                chat_id=1001,
                chat_type="private",
                sent_at=start_at + timedelta(seconds=idx * step_seconds),
            )

            responses = []
            if mycel.handle(event) is not None:
                responses.append("mycel")
            if openclaw.handle(event) is not None:
                responses.append("openclaw")

            print(f"[{event.sent_at.isoformat()}] {text!r} -> responders={responses}")

            if len(responses) > 1:
                double_handled += 1

            owner = expected_owner(text)
            if owner == "mycel":
                assert responses == ["mycel"], f"Expected mycel only for {text}, got {responses}"
            elif owner == "openclaw":
                assert responses == ["openclaw"], f"Expected openclaw only for {text}, got {responses}"
            elif owner == "shared-single":
                assert len(responses) == 1, f"Expected one responder for {text}, got {responses}"
            elif owner == "none":
                assert responses == [], f"Expected no responders for {text}, got {responses}"

        assert double_handled == 0, f"Expected zero double-handled commands, got {double_handled}"
        print("RESULT: 0 double-handled commands out of 20")

        run_edge_cases(mycel, openclaw)


def run_edge_cases(mycel: MycelBot, openclaw: OpenClawBotSimulator) -> None:
    edge_1 = MessageEvent(text="/m_ping", chat_id=2001)
    assert mycel.handle(edge_1) is not None
    assert openclaw.handle(edge_1) is None
    print("EDGE: /m_ping visible to OpenClaw -> ignored by OpenClaw")

    edge_2 = MessageEvent(text="/oc_status", chat_id=3001, chat_type="group")
    assert mycel.handle(edge_2) is None
    assert openclaw.handle(edge_2) is not None
    print("EDGE: group chat namespace -> only OpenClaw handles /oc_status")

    edge_3 = MessageEvent(text="hello there", chat_id=3001, chat_type="group")
    assert mycel.handle(edge_3) is not None
    assert openclaw.handle(edge_3) is None
    print("EDGE: ambiguous plain text -> claimed by Mycel default handler")


if __name__ == "__main__":
    run_simulation()
