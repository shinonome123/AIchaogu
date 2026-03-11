#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPS_ENV="${OPS_ENV:-$ROOT/.ops.env}"

if [[ -f "$OPS_ENV" ]]; then
  set -a
  . "$OPS_ENV"
  set +a
fi

RUN_DIR="${SIM_TRADING_RUN_DIR:-$ROOT/.ops/run}"

stop_service() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name not running"
    return 0
  fi

  local pid
  pid="$(<"$pid_file")"
  if [[ -z "$pid" ]]; then
    rm -f "$pid_file"
    echo "$name pid file was empty"
    return 0
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    echo "$name stale pid removed"
    return 0
  fi

  kill "$pid"
  for _ in {1..10}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$pid_file"
      echo "$name stopped"
      return 0
    fi
    sleep 1
  done

  echo "failed to stop $name pid=$pid" >&2
  return 1
}

stop_service dashboard
stop_service webhook
"$ROOT/scripts/ops_start.sh"
