from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


PROMPT_FILES = ["SOUL.md", "USER.md", "MEMORY.md", "AGENTS.md"]


def build_system_prompt(workspace_dir: Path) -> str:
    sections: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    sections.append(f"Current UTC time: {now}")

    for filename in PROMPT_FILES:
        path = workspace_dir / filename
        if not path.exists() or not path.is_file():
            continue
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        sections.append(f"[{filename}]\n{content}")

    if len(sections) == 1:
        sections.append("You are Mycel. Be concise, direct, and useful.")

    return "\n\n".join(sections)
