from __future__ import annotations

import fcntl
import json
import os
import socket
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_RUNTIME_DIR = Path(".run")


@dataclass(frozen=True)
class RuntimeState:
    pid: int
    command: str


def runtime_dir_from_env() -> Path:
    return Path(os.getenv("MYCEL_RUNTIME_DIR", DEFAULT_RUNTIME_DIR))


def ensure_runtime_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_runtime_state(path: Path) -> RuntimeState | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    pid = data.get("pid")
    command = data.get("command")
    if not isinstance(pid, int) or not isinstance(command, str):
        return None
    return RuntimeState(pid=pid, command=command)


def write_runtime_state(path: Path, state: RuntimeState) -> None:
    path.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")


def parse_host_port(address: str, default_port: int = 7233) -> tuple[str, int]:
    host, sep, port_text = address.rpartition(":")
    if not sep:
        return address, default_port
    if not host:
        raise ValueError(f"Invalid address: {address}")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(f"Invalid address: {address}") from exc
    return host, port


def temporal_is_reachable(address: str, timeout_seconds: float = 1.0) -> bool:
    host, port = parse_host_port(address)
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


class SingletonPidFile(AbstractContextManager["SingletonPidFile"]):
    def __init__(self, runtime_dir: Path, name: str, command: str):
        self._runtime_dir = ensure_runtime_dir(runtime_dir)
        self._name = name
        self._command = command
        self._lock_path = self._runtime_dir / f"{name}.lock"
        self._state_path = self._runtime_dir / f"{name}.pid"
        self._fd = None

    @property
    def state_path(self) -> Path:
        return self._state_path

    def __enter__(self) -> "SingletonPidFile":
        self._fd = self._lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            existing = read_runtime_state(self._state_path)
            if existing and pid_is_running(existing.pid):
                raise RuntimeError(
                    f"{self._name} is already running with pid {existing.pid}"
                ) from exc
            raise RuntimeError(f"{self._name} is already locked by another process") from exc

        self._fd.seek(0)
        self._fd.truncate()
        self._fd.write(f"{os.getpid()}\n")
        self._fd.flush()
        write_runtime_state(
            self._state_path,
            RuntimeState(pid=os.getpid(), command=self._command),
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._state_path.exists():
                self._state_path.unlink()
        finally:
            if self._fd is not None:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
                self._fd.close()
                self._fd = None
