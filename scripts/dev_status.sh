#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/dev_runtime.sh"

SUPERVISOR_STATE="$(runtime_state "${RUNTIME_DIR}/supervisor.pid")"
if [[ -n "$SUPERVISOR_STATE" ]]; then
  SUPERVISOR_PID="${SUPERVISOR_STATE%%|*}"
  if pid_is_running "$SUPERVISOR_PID"; then
    echo "supervisor: running (pid=${SUPERVISOR_PID})"
  else
    echo "supervisor: stale pid file (pid=${SUPERVISOR_PID})"
  fi
else
  echo "supervisor: stopped"
fi

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
