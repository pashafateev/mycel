from __future__ import annotations

import asyncio
from typing import Any

from tb01.bot import BotDeps, replay_update_payload


class RecordingWorkflowHandle:
    def __init__(self) -> None:
        self.signals: list[dict[str, Any]] = []

    async def signal(self, _name: str, payload: dict[str, Any]) -> None:
        self.signals.append(payload)


def _build_payload(update_id: int, message_id: int, text: str, chat_id: int = 4242) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


def _build_replay_stream() -> list[dict[str, Any]]:
    unique_payloads = [_build_payload(5000 + i, i + 1, f"tb02-msg-{i + 1}") for i in range(30)]
    duplicate_payloads = [
        unique_payloads[2],
        unique_payloads[7],
        unique_payloads[11],
        unique_payloads[19],
        unique_payloads[26],
    ]

    replay_stream = list(unique_payloads)

    # Intentionally reorder three messages (6, 7, 8 -> 8, 6, 7) to emulate out-of-order delivery.
    replay_stream[5], replay_stream[6], replay_stream[7] = (
        replay_stream[7],
        replay_stream[5],
        replay_stream[6],
    )

    replay_stream.extend(duplicate_payloads)
    return replay_stream


async def run() -> None:
    handle = RecordingWorkflowHandle()
    deps = BotDeps(workflow_handle=handle)  # type: ignore[arg-type]

    replay_stream = _build_replay_stream()
    for payload in replay_stream:
        envelope = await replay_update_payload(payload, deps)
        if envelope is None:
            continue
        await handle.signal("enqueue_ping", envelope)

    seen_update_ids = {signal["update_id"] for signal in handle.signals}
    seen_sequences = {signal["sequence"] for signal in handle.signals}

    assert len(replay_stream) == 35
    assert len(handle.signals) == 30, "Duplicate updates should be dropped before signaling"
    assert len(seen_update_ids) == 30
    assert len(seen_sequences) == 30
    assert seen_sequences == set(range(1, 31))

    ordering_regressions = 0
    last_sequence = 0
    for signal in handle.signals:
        sequence = signal["sequence"]
        if sequence < last_sequence:
            ordering_regressions += 1
        last_sequence = sequence

    assert ordering_regressions >= 1, "Replay should include out-of-order deliveries"

    print("TB2 idempotency replay passed")
    print(f"input_updates={len(replay_stream)}")
    print(f"unique_signals={len(handle.signals)}")
    print(f"ordering_regressions={ordering_regressions}")


if __name__ == "__main__":
    asyncio.run(run())
