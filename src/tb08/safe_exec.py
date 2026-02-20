from __future__ import annotations

import asyncio
import os
import shlex
import signal
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence

MAX_OUTPUT_BYTES = 10 * 1024
DEFAULT_TIMEOUT_SECONDS = 30


class ExecStatus(str, Enum):
    BLOCKED = "BLOCKED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


@dataclass
class ExecResult:
    command: str
    status: ExecStatus
    exit_code: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    reason: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    pid: Optional[int] = None
    attempt: int = 1


@dataclass
class ExecPolicy:
    workspace_dir: Path
    allowed_prefixes: tuple[str, ...] = (
        "ls",
        "cat",
        "echo",
        "git",
        "python",
        "pip",
        "grep",
        "find",
        "wc",
    )
    default_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = MAX_OUTPUT_BYTES


_SHELL_META = {"|", "||", "&&", ";", "<", ">", ">>", "2>", "&"}
_DANGEROUS_PY_PATTERNS = (
    "os.system",
    "subprocess",
    "shutil.rmtree",
    "rm -rf",
    "pathlib.Path(\"/\").rmdir",
)


def _resolve_workspace(workspace_dir: Path) -> Path:
    return workspace_dir.expanduser().resolve()


def _is_allowed_command(cmd: str, allowed_prefixes: Sequence[str]) -> bool:
    return any(cmd == prefix or cmd.startswith(f"{prefix}") for prefix in allowed_prefixes)


def _contains_shell_meta(tokens: Sequence[str]) -> bool:
    return any(token in _SHELL_META for token in tokens)


def _is_path_token(token: str) -> bool:
    if token.startswith("-"):
        return False
    if token in {".", ".."}:
        return True
    if token.startswith("/") or token.startswith("./") or token.startswith("../"):
        return True
    return False


def _is_within_workspace(token: str, workspace: Path) -> bool:
    candidate = Path(token).expanduser()
    if not candidate.is_absolute():
        candidate = (workspace / candidate).resolve()
    else:
        candidate = candidate.resolve()

    workspace = workspace.resolve()
    try:
        candidate.relative_to(workspace)
        return True
    except ValueError:
        return False


def _validate_command(command: str, policy: ExecPolicy) -> tuple[bool, str, list[str]]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        return False, f"Invalid command syntax: {exc}", []

    if not tokens:
        return False, "Empty command is not allowed", []

    program = tokens[0]
    if not _is_allowed_command(program, policy.allowed_prefixes):
        return False, f"Command '{program}' is not in allowlist", tokens

    if _contains_shell_meta(tokens):
        return False, "Shell operators/redirection are blocked; run direct commands only", tokens

    if program.startswith("python") and "-c" in tokens:
        idx = tokens.index("-c")
        if idx + 1 < len(tokens):
            code = tokens[idx + 1]
            if any(pattern in code for pattern in _DANGEROUS_PY_PATTERNS):
                return False, "Inline Python contains blocked process-execution patterns", tokens

    workspace = _resolve_workspace(policy.workspace_dir)
    for token in tokens[1:]:
        if _is_path_token(token) and not _is_within_workspace(token, workspace):
            return False, f"Path '{token}' is outside workspace scope '{workspace}'", tokens

    return True, "", tokens


def _truncate_output(data: bytes, max_bytes: int) -> tuple[str, bool]:
    if len(data) <= max_bytes:
        return data.decode("utf-8", errors="replace"), False
    return data[:max_bytes].decode("utf-8", errors="replace"), True


async def run_safe_exec(
    command: str,
    policy: ExecPolicy,
    timeout_seconds: Optional[int] = None,
    attempt: int = 1,
) -> ExecResult:
    is_valid, reason, tokens = _validate_command(command, policy)
    if not is_valid:
        return ExecResult(
            command=command,
            status=ExecStatus.BLOCKED,
            exit_code=None,
            stdout="",
            stderr="",
            timed_out=False,
            duration_ms=0,
            reason=reason,
            attempt=attempt,
        )

    timeout = timeout_seconds or policy.default_timeout_seconds
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *tokens,
        cwd=str(_resolve_workspace(policy.workspace_dir)),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    timed_out = False
    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout_raw, stderr_raw = await proc.communicate()

    duration_ms = int((time.monotonic() - start) * 1000)
    stdout, stdout_truncated = _truncate_output(stdout_raw or b"", policy.max_output_bytes)
    stderr, stderr_truncated = _truncate_output(stderr_raw or b"", policy.max_output_bytes)

    if timed_out:
        return ExecResult(
            command=command,
            status=ExecStatus.TIMEOUT,
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            duration_ms=duration_ms,
            reason=f"Command exceeded timeout of {timeout}s and was killed",
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            pid=proc.pid,
            attempt=attempt,
        )

    if proc.returncode == 0:
        return ExecResult(
            command=command,
            status=ExecStatus.SUCCESS,
            exit_code=0,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            duration_ms=duration_ms,
            reason="Command completed successfully",
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            pid=proc.pid,
            attempt=attempt,
        )

    return ExecResult(
        command=command,
        status=ExecStatus.ERROR,
        exit_code=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        duration_ms=duration_ms,
        reason=f"Command exited with status {proc.returncode}",
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        pid=proc.pid,
        attempt=attempt,
    )
