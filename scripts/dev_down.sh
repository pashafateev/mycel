#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/dev_runtime.sh"

SUPERVISOR_PID="$(runtime_pid "${RUNTIME_DIR}/supervisor.pid")"
if [[ -n "$SUPERVISOR_PID" ]]; then
  stop_pid "$SUPERVISOR_PID" "Mycel supervisor"
fi

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
  "${RUNTIME_DIR}/supervisor.pid" \
  "${RUNTIME_DIR}/supervisor.lock" \
  "${RUNTIME_DIR}/temporal.pid" \
  "$TEMPORAL_STATE"

echo "Local runtime state cleaned."
