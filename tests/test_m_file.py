from pathlib import Path

import pytest

from mycel.tools.m_file import (
    MAX_READ_CHARS,
    MAX_WRITE_CHARS,
    read_file,
    resolve_workspace_relative_path,
    write_file,
)


def test_resolve_workspace_relative_path_rejects_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError):
        resolve_workspace_relative_path(workspace, "../outside.txt")


def test_resolve_workspace_relative_path_rejects_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    symlink = workspace / "link"
    symlink.symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(ValueError):
        resolve_workspace_relative_path(workspace, "link/secret.txt")


def test_read_file_caps_output(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "notes.txt"
    target.write_text("x" * (MAX_READ_CHARS + 50), encoding="utf-8")

    result = read_file(workspace, "notes.txt")

    assert len(result) > MAX_READ_CHARS
    assert result.endswith("...(truncated)")
    assert result[:MAX_READ_CHARS] == "x" * MAX_READ_CHARS


def test_read_file_redacts_secret_values(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / ".env"
    target.write_text("OPENROUTER_API_KEY=abc123\nsafe=yes\n", encoding="utf-8")

    result = read_file(workspace, ".env")

    assert "abc123" not in result
    assert "OPENROUTER_API_KEY=[REDACTED]" in result
    assert "safe=yes" in result


def test_write_file_rejects_oversized_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError):
        write_file(workspace, "big.txt", "x" * (MAX_WRITE_CHARS + 1))


def test_write_file_writes_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    target = write_file(workspace, "memory/new.txt", "hello")

    assert target == workspace / "memory" / "new.txt"
    assert target.read_text(encoding="utf-8") == "hello"
