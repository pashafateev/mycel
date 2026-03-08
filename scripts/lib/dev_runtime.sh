#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="${ROOT_DIR}/.run"
LOG_DIR="${ROOT_DIR}/logs"
MYCEL_LOG="${LOG_DIR}/mycel.log"
SUPERVISOR_LOG="${LOG_DIR}/mycel-supervisor.log"
TEMPORAL_LOG="${LOG_DIR}/temporal.log"
TEMPORAL_STATE="${RUNTIME_DIR}/temporal.started_by_dev_up"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi

TEMPORAL_ADDRESS="${TEMPORAL_ADDRESS:-localhost:7233}"
TEMPORAL_NAMESPACE="${TEMPORAL_NAMESPACE:-default}"
MYCEL_TASK_QUEUE="${MYCEL_TASK_QUEUE:-mycel-phase1}"
export TEMPORAL_ADDRESS TEMPORAL_NAMESPACE MYCEL_TASK_QUEUE

if [[ -x /opt/homebrew/bin/python3.11 ]]; then
  PYTHON_BIN="/opt/homebrew/bin/python3.11"
else
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
fi

mkdir -p "$RUNTIME_DIR" "$LOG_DIR"
TEMPORAL_STARTED_BY_SCRIPT=0

runtime_pid() {
  local path="$1"
  PYTHONPATH=src "$PYTHON_BIN" - "$path" <<'PY'
from pathlib import Path
import sys
from mycel.lifecycle import read_runtime_state

state = read_runtime_state(Path(sys.argv[1]))
print("" if state is None else state.pid)
PY
}

runtime_state() {
  local path="$1"
  PYTHONPATH=src "$PYTHON_BIN" - "$path" <<'PY'
from pathlib import Path
import sys
from mycel.lifecycle import read_runtime_state

state = read_runtime_state(Path(sys.argv[1]))
if state is None:
    print("")
else:
    print(f"{state.pid}|{state.command}")
PY
}

pid_is_running() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  kill -0 "$pid" >/dev/null 2>&1
}

temporal_is_reachable() {
  PYTHONPATH=src "$PYTHON_BIN" - <<'PY'
import os
from mycel.lifecycle import temporal_is_reachable

raise SystemExit(0 if temporal_is_reachable(os.environ["TEMPORAL_ADDRESS"]) else 1)
PY
}

write_runtime_state() {
  local path="$1"
  local pid="$2"
  local command_name="$3"
  PYTHONPATH=src "$PYTHON_BIN" - "$path" "$pid" "$command_name" <<'PY'
from pathlib import Path
import sys
from mycel.lifecycle import RuntimeState, write_runtime_state

write_runtime_state(
    Path(sys.argv[1]),
    RuntimeState(pid=int(sys.argv[2]), command=sys.argv[3]),
)
PY
}

stop_pid() {
  local pid="$1"
  local label="$2"
  if ! pid_is_running "$pid"; then
    return 0
  fi

  kill -TERM "$pid" >/dev/null 2>&1 || true
  for _ in {1..10}; do
    if ! pid_is_running "$pid"; then
      echo "Stopped ${label} (${pid})."
      return 0
    fi
    sleep 1
  done

  kill -KILL "$pid" >/dev/null 2>&1 || true
  echo "Force-stopped ${label} (${pid})."
}

cleanup_managed_temporal() {
  if [[ "$TEMPORAL_STARTED_BY_SCRIPT" == "1" ]] && [[ -n "${TEMPORAL_PID:-}" ]] && pid_is_running "$TEMPORAL_PID"; then
    kill -TERM "$TEMPORAL_PID" >/dev/null 2>&1 || true
  fi
  if [[ "$TEMPORAL_STARTED_BY_SCRIPT" == "1" ]]; then
    rm -f "${RUNTIME_DIR}/temporal.pid" "$TEMPORAL_STATE"
  fi
}

ensure_temporal() {
  if temporal_is_reachable; then
    echo "Temporal is reachable at ${TEMPORAL_ADDRESS}."
    return 0
  fi

  if ! command -v temporal >/dev/null 2>&1; then
    echo "Temporal is not reachable at ${TEMPORAL_ADDRESS}, and the 'temporal' CLI is not installed." >&2
    return 1
  fi

  : > "$TEMPORAL_LOG"
  nohup temporal server start-dev >"$TEMPORAL_LOG" 2>&1 &
  TEMPORAL_PID="$!"
  TEMPORAL_STARTED_BY_SCRIPT=1
  write_runtime_state "${RUNTIME_DIR}/temporal.pid" "$TEMPORAL_PID" "temporal server start-dev"
  printf "1\n" > "$TEMPORAL_STATE"
  echo "Starting local Temporal dev server (pid ${TEMPORAL_PID})..."

  for _ in {1..30}; do
    if temporal_is_reachable; then
      return 0
    fi
    if ! pid_is_running "$TEMPORAL_PID"; then
      echo "Temporal failed to start. See ${TEMPORAL_LOG}" >&2
      return 1
    fi
    sleep 1
  done

  if pid_is_running "$TEMPORAL_PID"; then
    kill -TERM "$TEMPORAL_PID" >/dev/null 2>&1 || true
  fi
  rm -f "${RUNTIME_DIR}/temporal.pid" "$TEMPORAL_STATE"
  echo "Temporal did not become reachable at ${TEMPORAL_ADDRESS}. See ${TEMPORAL_LOG}" >&2
  return 1
}
