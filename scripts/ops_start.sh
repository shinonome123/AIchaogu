#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPS_ENV="${OPS_ENV:-$ROOT/.ops.env}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ -f "$OPS_ENV" ]]; then
  set -a
  . "$OPS_ENV"
  set +a
fi

STATE_DIR="${SIM_TRADING_STATE_DIR:-$ROOT/demo/state}"
REPORT_LOG="${SIM_TRADING_REPORT_LOG:-$ROOT/demo/reports-log.jsonl}"
DASHBOARD_HOST="${SIM_TRADING_DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_PORT="${SIM_TRADING_DASHBOARD_PORT:-8780}"
WEBHOOK_HOST="${SIM_TRADING_WEBHOOK_HOST:-127.0.0.1}"
WEBHOOK_PORT="${SIM_TRADING_WEBHOOK_PORT:-8765}"
RUN_DIR="${SIM_TRADING_RUN_DIR:-$ROOT/.ops/run}"
LOG_DIR="${SIM_TRADING_LOG_DIR:-$ROOT/.ops/logs}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

start_service() {
  local name="$1"
  shift

  local pid_file="$RUN_DIR/$name.pid"
  local log_file="$LOG_DIR/$name.log"
  local pid=""

  if [[ -f "$pid_file" ]]; then
    pid="$(<"$pid_file")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$name already running pid=$pid log=$log_file"
      return 0
    fi
    rm -f "$pid_file"
  fi

  nohup "$@" >>"$log_file" 2>&1 &
  pid="$!"
  echo "$pid" >"$pid_file"
  sleep 1

  if kill -0 "$pid" 2>/dev/null; then
    echo "started $name pid=$pid log=$log_file"
    return 0
  fi

  echo "failed to start $name; inspect $log_file" >&2
  return 1
}

start_service dashboard \
  "$PYTHON_BIN" -m sim_trading \
  --state-dir "$STATE_DIR" \
  serve-dashboard \
  --report-log "$REPORT_LOG" \
  --host "$DASHBOARD_HOST" \
  --port "$DASHBOARD_PORT"

start_service webhook \
  "$PYTHON_BIN" -m sim_trading \
  --state-dir "$STATE_DIR" \
  serve-webhook \
  --report-log "$REPORT_LOG" \
  --host "$WEBHOOK_HOST" \
  --port "$WEBHOOK_PORT"

echo "ops start complete"
