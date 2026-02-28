#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${TELEGRAM_BOT_TOKEN_MY:-}" ]]; then
  echo "TELEGRAM_BOT_TOKEN_MY is required"
  exit 1
fi

if [[ -z "${TELEGRAM_BOT_TOKEN_OC:-}" ]]; then
  echo "TELEGRAM_BOT_TOKEN_OC is required"
  exit 1
fi

TEMPORAL_ADDRESS="${TEMPORAL_ADDRESS:-localhost:7233}"
TEMPORAL_HOST="${TEMPORAL_ADDRESS%:*}"
TEMPORAL_PORT="${TEMPORAL_ADDRESS##*:}"
RUNTIME_SECONDS="${TB10_RUNTIME_SECONDS:-1800}"
TEMPORAL_PID=""
MYCEL_PID=""
OPENCLAW_PID=""

cleanup() {
  if [[ -n "${MYCEL_PID}" ]]; then
    kill "${MYCEL_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${OPENCLAW_PID}" ]]; then
    kill "${OPENCLAW_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${TEMPORAL_PID}" ]]; then
    kill "${TEMPORAL_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if nc -z "${TEMPORAL_HOST}" "${TEMPORAL_PORT}" >/dev/null 2>&1; then
  echo "Temporal server reachable at ${TEMPORAL_ADDRESS}"
else
  if ! command -v temporal >/dev/null 2>&1; then
    echo "Temporal server is not reachable and 'temporal' CLI is not installed."
    echo "Install Temporal CLI or start a server manually, then retry."
    exit 1
  fi

  echo "Starting Temporal dev server on ${TEMPORAL_ADDRESS}"
  temporal server start-dev --db-filename /tmp/mycel-tb10.db >/tmp/mycel-tb10-temporal.log 2>&1 &
  TEMPORAL_PID=$!

  for _ in $(seq 1 30); do
    if nc -z "${TEMPORAL_HOST}" "${TEMPORAL_PORT}" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ! nc -z "${TEMPORAL_HOST}" "${TEMPORAL_PORT}" >/dev/null 2>&1; then
    echo "Temporal dev server did not become reachable."
    echo "See /tmp/mycel-tb10-temporal.log for details."
    exit 1
  fi
fi

echo "Starting TB10 Mycel bot (/m_*) and OpenClaw dummy bot (/oc_*)."
echo "Logs:"
echo "  /tmp/mycel-tb10-mycel.log"
echo "  /tmp/mycel-tb10-openclaw.log"

PYTHONPATH=src python3 -m tb10.mycel_bot >/tmp/mycel-tb10-mycel.log 2>&1 &
MYCEL_PID=$!
PYTHONPATH=src python3 -m tb10.openclaw_dummy_bot >/tmp/mycel-tb10-openclaw.log 2>&1 &
OPENCLAW_PID=$!

echo "Both bots started. Demo runtime: ${RUNTIME_SECONDS}s"
echo "Try commands in a chat where both bots are present:"
echo "  /m_help"
echo "  /oc_help"
echo "  /m_ping hello"
echo "  /oc_ping hello"
echo "  /ping hello      (should be ignored by both)"

sleep "${RUNTIME_SECONDS}"
echo "TB10 demo runtime complete. Stopping bots."

