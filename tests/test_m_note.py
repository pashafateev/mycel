from datetime import date
from pathlib import Path

import pytest

from mycel.tools.m_note import append_note, ensure_within_workspace


def test_ensure_within_workspace_blocks_outside_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.md"

    with pytest.raises(ValueError):
        ensure_within_workspace(workspace, outside)


def test_append_note_writes_inside_workspace_memory_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    note_path = append_note(workspace, "remember this", note_date=date(2026, 3, 1))

    assert note_path == workspace / "memory" / "2026-03-01.md"
    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert "remember this" in content
