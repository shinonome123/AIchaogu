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

describe_pid() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"
  local log_file="$LOG_DIR/$name.log"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name down pid_file=$pid_file log=$log_file"
    return 1
  fi

  local pid
  pid="$(<"$pid_file")"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "$name up pid=$pid log=$log_file"
    return 0
  fi

  echo "$name stale pid=$pid pid_file=$pid_file log=$log_file"
  return 1
}

describe_pid dashboard || true
describe_pid webhook || true

"$PYTHON_BIN" -m sim_trading \
  --state-dir "$STATE_DIR" \
  health-check \
  --report-log "$REPORT_LOG" \
  --dashboard-pid-file "$RUN_DIR/dashboard.pid" \
  --webhook-pid-file "$RUN_DIR/webhook.pid" \
  --dashboard-health-url "http://$DASHBOARD_HOST:$DASHBOARD_PORT/api/health" \
  --webhook-host "$WEBHOOK_HOST" \
  --webhook-port "$WEBHOOK_PORT"
