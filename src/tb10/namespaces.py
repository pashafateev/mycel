from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_COMMAND_RE = re.compile(r"^/(?P<command>[A-Za-z0-9_]+)(?:@[A-Za-z0-9_]+)?(?:\s+(?P<args>.*))?$")


@dataclass(frozen=True)
class RoutedCommand:
    command: str
    args: str


def parse_namespaced_command(text: str, namespace: str) -> Optional[RoutedCommand]:
    match = _COMMAND_RE.match((text or "").strip())
    if not match:
        return None

    command = match.group("command")
    prefix = f"{namespace}_"
    if not command.startswith(prefix):
        return None

    return RoutedCommand(
        command=command[len(prefix) :],
        args=(match.group("args") or "").strip(),
    )

