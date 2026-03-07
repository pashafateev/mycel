#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="${ROOT_DIR}/.run"
LOG_DIR="${ROOT_DIR}/logs"
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

MYCEL_STATE="$(runtime_state "${RUNTIME_DIR}/mycel.pid")"
if [[ -n "$MYCEL_STATE" ]]; then
  MYCEL_PID="${MYCEL_STATE%%|*}"
  if pid_is_running "$MYCEL_PID"; then
    echo "mycel: running (pid=${MYCEL_PID})"
  else
    echo "mycel: stale pid file (pid=${MYCEL_PID})"
  fi
else
  echo "mycel: stopped"
fi

TEMPORAL_STATE_LINE="$(runtime_state "${RUNTIME_DIR}/temporal.pid")"
if [[ -n "$TEMPORAL_STATE_LINE" ]]; then
  TEMPORAL_PID="${TEMPORAL_STATE_LINE%%|*}"
else
  TEMPORAL_PID=""
fi

if temporal_is_reachable; then
  if [[ -f "$TEMPORAL_STATE" ]] && pid_is_running "$TEMPORAL_PID"; then
    echo "temporal: reachable (managed pid=${TEMPORAL_PID})"
  else
    echo "temporal: reachable (${TEMPORAL_ADDRESS})"
  fi
else
  if [[ -n "$TEMPORAL_PID" ]] && ! pid_is_running "$TEMPORAL_PID"; then
    echo "temporal: not reachable (stale pid=${TEMPORAL_PID})"
  else
    echo "temporal: not reachable (${TEMPORAL_ADDRESS})"
  fi
fi

echo "namespace: ${TEMPORAL_NAMESPACE}"
echo "task_queue: ${MYCEL_TASK_QUEUE}"
echo "runtime_dir: ${RUNTIME_DIR}"
echo "log_dir: ${LOG_DIR}"
