from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

from mycel.lifecycle import (
    SingletonPidFile,
    parse_host_port,
    pid_is_running,
    read_runtime_state,
    temporal_is_reachable,
)


def test_parse_host_port_supports_default_and_explicit_port() -> None:
    assert parse_host_port("localhost") == ("localhost", 7233)
    assert parse_host_port("127.0.0.1:9000") == ("127.0.0.1", 9000)


def test_singleton_pid_file_writes_and_cleans_state(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "run"
    state_path = runtime_dir / "mycel.pid"

    with SingletonPidFile(runtime_dir, "mycel", "bot+worker"):
        state = read_runtime_state(state_path)
        assert state is not None
        assert state.pid == os.getpid()
        assert state.command == "bot+worker"
        assert pid_is_running(state.pid) is True

    assert read_runtime_state(state_path) is None


def test_singleton_pid_file_rejects_second_process(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "run"
    repo_root = Path(__file__).resolve().parents[1]
    script = """
from pathlib import Path
import sys
from mycel.lifecycle import SingletonPidFile

try:
    with SingletonPidFile(Path(sys.argv[1]), "mycel", "bot+worker"):
        pass
except RuntimeError as exc:
    print(str(exc))
    raise SystemExit(23)

raise SystemExit(0)
"""

    with SingletonPidFile(runtime_dir, "mycel", "bot+worker"):
        completed = subprocess.run(
            [sys.executable, "-c", script, str(runtime_dir)],
            capture_output=True,
            text=True,
            cwd=repo_root,
            env={**os.environ, "PYTHONPATH": str(repo_root / "src")},
            check=False,
        )

    assert completed.returncode == 23
    assert "already running" in completed.stdout


def test_temporal_is_reachable_detects_listening_socket() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        host, port = server.getsockname()

        assert temporal_is_reachable(f"{host}:{port}", timeout_seconds=0.2) is True

    assert temporal_is_reachable(f"{host}:{port}", timeout_seconds=0.2) is False
