#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/dev_runtime.sh"

MYCEL_PID="$(runtime_pid "${RUNTIME_DIR}/mycel.pid")"
SUPERVISOR_PID="$(runtime_pid "${RUNTIME_DIR}/supervisor.pid")"
if pid_is_running "$SUPERVISOR_PID"; then
  echo "Mycel supervisor is already running with pid ${SUPERVISOR_PID}."
  echo "Use scripts/dev_status.sh for details or scripts/dev_down.sh to stop it."
  exit 1
fi

if pid_is_running "$MYCEL_PID"; then
  echo "Mycel is already running with pid ${MYCEL_PID}."
  echo "Use scripts/dev_status.sh for details or scripts/dev_down.sh to stop it."
  exit 1
fi

rm -f "${RUNTIME_DIR}/mycel.pid"

if ! ensure_temporal; then
  exit 1
fi

mkdir -p "$LOG_DIR"
: > "$MYCEL_LOG"
nohup env \
  PYTHONPATH=src \
  MYCEL_RUNTIME_DIR="$RUNTIME_DIR" \
  "$PYTHON_BIN" -u scripts/run_phase1_bot.py >"$MYCEL_LOG" 2>&1 &
MYCEL_SPAWN_PID="$!"

for _ in {1..15}; do
  if ! pid_is_running "$MYCEL_SPAWN_PID"; then
    cleanup_managed_temporal
    echo "Mycel exited during startup. See ${MYCEL_LOG}" >&2
    exit 1
  fi

  MYCEL_PID="$(runtime_pid "${RUNTIME_DIR}/mycel.pid")"
  if pid_is_running "$MYCEL_PID"; then
    break
  fi
  sleep 1
done

MYCEL_PID="$(runtime_pid "${RUNTIME_DIR}/mycel.pid")"
if ! pid_is_running "$MYCEL_PID"; then
  cleanup_managed_temporal
  echo "Mycel did not finish startup. See ${MYCEL_LOG}" >&2
  exit 1
fi

echo "Mycel is running."
echo "  bot pid: ${MYCEL_PID}"
echo "  temporal: ${TEMPORAL_ADDRESS} (namespace=${TEMPORAL_NAMESPACE}, task_queue=${MYCEL_TASK_QUEUE})"
echo "  logs: ${MYCEL_LOG} ${TEMPORAL_LOG}"
echo "  status: scripts/dev_status.sh"
echo "  stop: scripts/dev_down.sh"
