#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "TELEGRAM_BOT_TOKEN is required"
  exit 1
fi

TEMPORAL_ADDRESS="${TEMPORAL_ADDRESS:-localhost:7233}"
TEMPORAL_HOST="${TEMPORAL_ADDRESS%:*}"
TEMPORAL_PORT="${TEMPORAL_ADDRESS##*:}"
TEMPORAL_PID=""

cleanup() {
  if [[ -n "${TEMPORAL_PID}" ]]; then
    echo "Stopping temporary Temporal dev server (pid ${TEMPORAL_PID})"
    kill "${TEMPORAL_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if nc -z "${TEMPORAL_HOST}" "${TEMPORAL_PORT}" >/dev/null 2>&1; then
  echo "Temporal server reachable at ${TEMPORAL_ADDRESS}"
else
  if ! command -v temporal >/dev/null 2>&1; then
    echo "Temporal server is not reachable and 'temporal' CLI is not installed."
    echo "Install Temporal CLI or start a server manually, then retry."
    exit 1
  fi

  echo "Starting Temporal dev server on ${TEMPORAL_ADDRESS}"
  temporal server start-dev --db-filename /tmp/mycel-tb01.db >/tmp/mycel-tb01-temporal.log 2>&1 &
  TEMPORAL_PID=$!

  for _ in $(seq 1 30); do
    if nc -z "${TEMPORAL_HOST}" "${TEMPORAL_PORT}" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ! nc -z "${TEMPORAL_HOST}" "${TEMPORAL_PORT}" >/dev/null 2>&1; then
    echo "Temporal dev server did not become reachable."
    echo "See /tmp/mycel-tb01-temporal.log for details."
    exit 1
  fi
fi

echo "Running TB1 app."
echo "Instruction: Send /ping hello (or any text) to your bot in Telegram."

PYTHONPATH=src python -m tb01.main
