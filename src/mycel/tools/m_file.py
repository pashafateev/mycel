from __future__ import annotations

import re
from pathlib import Path

MAX_READ_CHARS = 4000
MAX_WRITE_CHARS = 8000

_SENSITIVE_KEY_RE = re.compile(
    r"(?im)^([A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)\s*=\s*(.+)$"
)
_SENSITIVE_INLINE_RE = re.compile(
    r"(?i)\b(?:bearer|token|secret|password|api[_-]?key)\b\s*[:=]\s*([^\s,;]+)"
)


def ensure_within_workspace(workspace_dir: Path, target_path: Path) -> Path:
    workspace = workspace_dir.resolve()
    target = target_path.resolve()

    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("Refusing to access outside workspace.") from exc

    return target


def resolve_workspace_relative_path(workspace_dir: Path, relative_path: str) -> Path:
    raw = relative_path.strip()
    if not raw:
        raise ValueError("Path is required.")

    requested = Path(raw)
    if requested.is_absolute():
        raise ValueError("Path must be relative to workspace.")

    return ensure_within_workspace(workspace_dir, workspace_dir / requested)


def _redact_secrets(text: str) -> str:
    redacted = _SENSITIVE_KEY_RE.sub(r"\1=[REDACTED]", text)
    return _SENSITIVE_INLINE_RE.sub("[REDACTED]", redacted)


def read_file(workspace_dir: Path, relative_path: str, *, max_chars: int = MAX_READ_CHARS) -> str:
    target = resolve_workspace_relative_path(workspace_dir, relative_path)
    if not target.exists() or not target.is_file():
        raise ValueError("File not found.")

    content = target.read_text(encoding="utf-8", errors="replace")
    snippet = _redact_secrets(content[:max_chars])
    if len(content) > max_chars:
        snippet += "\n\n...(truncated)"
    return snippet


def write_file(
    workspace_dir: Path,
    relative_path: str,
    content: str,
    *,
    max_chars: int = MAX_WRITE_CHARS,
) -> Path:
    if len(content) > max_chars:
        raise ValueError(f"Content exceeds {max_chars} character limit.")

    target = resolve_workspace_relative_path(workspace_dir, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target
