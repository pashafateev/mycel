from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from mycel.lifecycle import SingletonPidFile, runtime_dir_from_env


LOGGER = logging.getLogger(__name__)
RESTART_DELAY_SECONDS = 3


class Supervisor:
    def __init__(self, runtime_dir: Path, log_path: Path, python_bin: str) -> None:
        self._runtime_dir = runtime_dir
        self._log_path = log_path
        self._python_bin = python_bin
        self._stop_requested = False
        self._child: subprocess.Popen[bytes] | None = None

    def request_stop(self, signum: int, _frame: object) -> None:
        LOGGER.info("Received signal %s; stopping supervisor", signum)
        self._stop_requested = True
        self._terminate_child()

    def run_forever(self) -> None:
        while not self._stop_requested:
            exit_code = self._run_once()
            if self._stop_requested:
                break

            LOGGER.warning(
                "Mycel exited unexpectedly with code %s; restarting in %s seconds",
                exit_code,
                RESTART_DELAY_SECONDS,
            )
            time.sleep(RESTART_DELAY_SECONDS)

    def _run_once(self) -> int:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path.cwd() / "src")
        env["MYCEL_RUNTIME_DIR"] = str(self._runtime_dir)

        with self._log_path.open("ab") as log_file:
            self._child = subprocess.Popen(
                [self._python_bin, "-u", "scripts/run_phase1_bot.py"],
                cwd=Path.cwd(),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            LOGGER.info("Started Mycel child process pid=%s", self._child.pid)
            return_code = self._child.wait()
            LOGGER.info("Mycel child process pid=%s exited with code=%s", self._child.pid, return_code)
            self._child = None
            return return_code

    def _terminate_child(self) -> None:
        if self._child is None or self._child.poll() is not None:
            return

        self._child.terminate()
        try:
            self._child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._child.kill()
            self._child.wait(timeout=5)


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("MYCEL_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    runtime_dir = runtime_dir_from_env()
    log_path = Path(os.getenv("MYCEL_LOG_PATH", "logs/mycel.log"))
    python_bin = sys.executable
    supervisor = Supervisor(runtime_dir=runtime_dir, log_path=log_path, python_bin=python_bin)

    signal.signal(signal.SIGTERM, supervisor.request_stop)
    signal.signal(signal.SIGINT, supervisor.request_stop)

    with SingletonPidFile(runtime_dir, "supervisor", "dev-supervisor"):
        LOGGER.info("Mycel supervisor started")
        supervisor.run_forever()
        LOGGER.info("Mycel supervisor stopped")


if __name__ == "__main__":
    main()
