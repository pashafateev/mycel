#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/dev_runtime.sh"

SUPERVISOR_PID="$(runtime_pid "${RUNTIME_DIR}/supervisor.pid")"
if pid_is_running "$SUPERVISOR_PID"; then
  echo "Mycel supervisor is already running with pid ${SUPERVISOR_PID}."
  echo "Use scripts/dev_status.sh for details or scripts/dev_down.sh to stop it."
  exit 1
fi

MYCEL_PID="$(runtime_pid "${RUNTIME_DIR}/mycel.pid")"
if pid_is_running "$MYCEL_PID"; then
  echo "Mycel is already running with pid ${MYCEL_PID}."
  echo "Stop it with scripts/dev_down.sh before starting the supervisor."
  exit 1
fi

rm -f "${RUNTIME_DIR}/supervisor.pid" "${RUNTIME_DIR}/mycel.pid"

if ! ensure_temporal; then
  exit 1
fi

: > "$SUPERVISOR_LOG"
nohup env \
  PYTHONPATH=src \
  MYCEL_RUNTIME_DIR="$RUNTIME_DIR" \
  MYCEL_LOG_PATH="$MYCEL_LOG" \
  "$PYTHON_BIN" -u -m mycel.dev_supervisor >"$SUPERVISOR_LOG" 2>&1 &
SUPERVISOR_SPAWN_PID="$!"

for _ in {1..15}; do
  if ! pid_is_running "$SUPERVISOR_SPAWN_PID"; then
    cleanup_managed_temporal
    echo "Mycel supervisor exited during startup. See ${SUPERVISOR_LOG}" >&2
    exit 1
  fi

  SUPERVISOR_PID="$(runtime_pid "${RUNTIME_DIR}/supervisor.pid")"
  MYCEL_PID="$(runtime_pid "${RUNTIME_DIR}/mycel.pid")"
  if pid_is_running "$SUPERVISOR_PID" && pid_is_running "$MYCEL_PID"; then
    break
  fi
  sleep 1
done

SUPERVISOR_PID="$(runtime_pid "${RUNTIME_DIR}/supervisor.pid")"
MYCEL_PID="$(runtime_pid "${RUNTIME_DIR}/mycel.pid")"
if ! pid_is_running "$SUPERVISOR_PID" || ! pid_is_running "$MYCEL_PID"; then
  if pid_is_running "$SUPERVISOR_PID"; then
    stop_pid "$SUPERVISOR_PID" "Mycel supervisor"
  fi
  cleanup_managed_temporal
  echo "Mycel supervisor did not finish startup. See ${SUPERVISOR_LOG} and ${MYCEL_LOG}" >&2
  exit 1
fi

echo "Mycel supervisor is running."
echo "  supervisor pid: ${SUPERVISOR_PID}"
echo "  bot pid: ${MYCEL_PID}"
echo "  temporal: ${TEMPORAL_ADDRESS} (namespace=${TEMPORAL_NAMESPACE}, task_queue=${MYCEL_TASK_QUEUE})"
echo "  logs: ${SUPERVISOR_LOG} ${MYCEL_LOG} ${TEMPORAL_LOG}"
echo "  status: scripts/dev_status.sh"
echo "  stop: scripts/dev_down.sh"
