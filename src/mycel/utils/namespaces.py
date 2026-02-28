from __future__ import annotations

import re
from dataclasses import dataclass


_NAMESPACE_RE = re.compile(
    r"^/(?P<namespace>[a-z0-9]+)_(?P<command>[a-z0-9_]+)(?:@[A-Za-z0-9_]+)?(?:\s+(?P<args>.*))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedNamespaceCommand:
    namespace: str
    command: str
    args: str

    @property
    def namespaced_command(self) -> str:
        return f"/{self.namespace}_{self.command}"


def parse_namespaced_command(text: str) -> ParsedNamespaceCommand | None:
    if not text:
        return None
    stripped = text.strip()
    match = _NAMESPACE_RE.match(stripped)
    if not match:
        return None
    namespace = match.group("namespace").lower()
    command = match.group("command").lower()
    args = (match.group("args") or "").strip()
    return ParsedNamespaceCommand(namespace=namespace, command=command, args=args)


def is_mycel_command(text: str) -> bool:
    parsed = parse_namespaced_command(text)
    return parsed is not None and parsed.namespace == "m"
