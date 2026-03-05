from __future__ import annotations

from datetime import date
from pathlib import Path

from mycel.tools.m_file import ensure_within_workspace


def append_note(workspace_dir: Path, text: str, *, note_date: date | None = None) -> Path:
    note_text = text.strip()
    if not note_text:
        raise ValueError("Usage: /m_note <text>")

    day = note_date or date.today()
    target = workspace_dir / "memory" / f"{day.isoformat()}.md"
    target = ensure_within_workspace(workspace_dir, target)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("a", encoding="utf-8") as handle:
        handle.write(f"- {note_text}\n")

    return target
