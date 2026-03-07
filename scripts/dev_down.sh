#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="${ROOT_DIR}/.run"
TEMPORAL_STATE="${RUNTIME_DIR}/temporal.started_by_dev_up"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi

if [[ -x /opt/homebrew/bin/python3.11 ]]; then
  PYTHON_BIN="/opt/homebrew/bin/python3.11"
else
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
fi

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

pid_is_running() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  kill -0 "$pid" >/dev/null 2>&1
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

MYCEL_PID="$(runtime_pid "${RUNTIME_DIR}/mycel.pid")"
if [[ -n "$MYCEL_PID" ]]; then
  stop_pid "$MYCEL_PID" "Mycel"
fi

if [[ -f "$TEMPORAL_STATE" ]]; then
  TEMPORAL_PID="$(runtime_pid "${RUNTIME_DIR}/temporal.pid")"
  if [[ -n "$TEMPORAL_PID" ]]; then
    stop_pid "$TEMPORAL_PID" "Temporal"
  fi
fi

rm -f \
  "${RUNTIME_DIR}/mycel.pid" \
  "${RUNTIME_DIR}/mycel.lock" \
  "${RUNTIME_DIR}/temporal.pid" \
  "$TEMPORAL_STATE"

echo "Local runtime state cleaned."
