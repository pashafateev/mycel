from __future__ import annotations

from datetime import date
from pathlib import Path


def ensure_within_workspace(workspace_dir: Path, target_path: Path) -> Path:
    workspace = workspace_dir.resolve()
    target = target_path.resolve()

    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("Refusing to write outside workspace.") from exc

    return target


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
