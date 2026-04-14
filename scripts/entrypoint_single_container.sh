#!/usr/bin/env bash
set -euo pipefail

PIDS=()

start_process() {
  local name="$1"
  shift

  echo "[entrypoint] starting ${name}: $*"
  "$@" &
  local pid=$!
  PIDS+=("${pid}")
  echo "[entrypoint] ${name} pid=${pid}"
}

shutdown() {
  echo "[entrypoint] shutting down child processes"
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  done

  wait || true
}

trap shutdown SIGINT SIGTERM

start_process "uvicorn-api" uvicorn app.main:App --host 0.0.0.0 --port 8000
start_process "ingestion-worker" celery -A app.celery_app worker -Q ingestion -c 2 --loglevel=info
start_process "beat-scheduler" celery -A app.celery_app beat --loglevel=info
start_process "nlp-subscriber" python -m app.domain.sentiment.event_subscriber

set +e
wait -n
exit_code=$?
set -e

echo "[entrypoint] a child process exited with code ${exit_code}; stopping remaining processes"
shutdown
exit "${exit_code}"
