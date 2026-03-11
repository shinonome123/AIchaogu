#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
STATE_DIR="${STATE_DIR:-$ROOT/demo/state}"
REPORT_LOG="${REPORT_LOG:-$ROOT/demo/reports-log.jsonl}"
REPORTS_DIR="${REPORTS_DIR:-$ROOT/demo/reports}"
MARKET_SOURCE="${MARKET_SOURCE:-binance}"
MARKET_API_ROOT="${MARKET_API_ROOT:-https://api.binance.com}"
UNIVERSE_API_ROOT="${UNIVERSE_API_ROOT:-https://api.binance.com}"
RUN_UNIVERSE_REFRESH="${RUN_UNIVERSE_REFRESH:-1}"
UNIVERSE_REFRESH_EVERY_MINUTES="${UNIVERSE_REFRESH_EVERY_MINUTES:-15}"
RUN_BASELINE_STRATEGY="${RUN_BASELINE_STRATEGY:-1}"
RUN_DS_CONSERVATIVE_STRATEGY="${RUN_DS_CONSERVATIVE_STRATEGY:-1}"
RUN_DS_AGGRESSIVE_STRATEGY="${RUN_DS_AGGRESSIVE_STRATEGY:-1}"
STRATEGY_RUN_EVERY_MINUTES="${STRATEGY_RUN_EVERY_MINUTES:-30}"
BASELINE_STRATEGY_EVERY_MINUTES="${BASELINE_STRATEGY_EVERY_MINUTES:-$STRATEGY_RUN_EVERY_MINUTES}"
DS_STRATEGY_EVERY_MINUTES="${DS_STRATEGY_EVERY_MINUTES:-$STRATEGY_RUN_EVERY_MINUTES}"
DS_CONSERVATIVE_STRATEGY_EVERY_MINUTES="${DS_CONSERVATIVE_STRATEGY_EVERY_MINUTES:-$DS_STRATEGY_EVERY_MINUTES}"
DS_AGGRESSIVE_STRATEGY_EVERY_MINUTES="${DS_AGGRESSIVE_STRATEGY_EVERY_MINUTES:-$DS_STRATEGY_EVERY_MINUTES}"
STRATEGY_LOOKBACK_POINTS="${STRATEGY_LOOKBACK_POINTS:-6}"
RUN_EXECUTE_SIM="${RUN_EXECUTE_SIM:-1}"
EXECUTE_SIM_NOTIFY="${EXECUTE_SIM_NOTIFY:-1}"
EXECUTE_LOOKBACK_POINTS="${EXECUTE_LOOKBACK_POINTS:-6}"
RUN_DS_SHADOW="${RUN_DS_SHADOW:-0}"
DS_SHADOW_EVERY_HOURS="${DS_SHADOW_EVERY_HOURS:-1}"
RUN_VALIDATE_STRATEGY="${RUN_VALIDATE_STRATEGY:-0}"
VALIDATE_EVERY_HOURS="${VALIDATE_EVERY_HOURS:-6}"
VALIDATE_LOOKBACK_POINTS="${VALIDATE_LOOKBACK_POINTS:-}"
VALIDATE_STEP_POINTS="${VALIDATE_STEP_POINTS:-}"
DISABLE_LEGACY_HOURLY="${DISABLE_LEGACY_HOURLY:-1}"
RUN_MARKER_DIR="${RUN_MARKER_DIR:-$ROOT/.ops/run}"

build_symbol_args() {
  local symbols="${MARKET_SYMBOLS:-}"
  local -a args=()
  if [[ -n "$symbols" ]]; then
    IFS=',' read -r -a raw_symbols <<< "$symbols"
    for symbol in "${raw_symbols[@]}"; do
      [[ -n "$symbol" ]] || continue
      args+=(--symbol "$symbol")
    done
  fi
  if ((${#args[@]})); then
    printf '%s\n' "${args[@]}"
  fi
}

should_run_interval() {
  local key="$1"
  local interval_minutes="$2"
  local now last file
  file="$RUN_MARKER_DIR/tick-${key}.ts"

  if (( interval_minutes < 1 )); then
    interval_minutes=1
  fi

  mkdir -p "$RUN_MARKER_DIR"
  now="$(date +%s)"
  if [[ ! -f "$file" ]]; then
    return 0
  fi

  last="$(cat "$file" 2>/dev/null || echo 0)"
  [[ "$last" =~ ^[0-9]+$ ]] || last=0

  if (( now - last >= interval_minutes * 60 )); then
    return 0
  fi
  return 1
}

mark_interval_run() {
  local key="$1"
  mkdir -p "$RUN_MARKER_DIR"
  date +%s > "$RUN_MARKER_DIR/tick-${key}.ts"
}

run_strategy_track() {
  local strategy="$1"
  "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" --report-log "$REPORT_LOG" strategy-run \
    --strategy "$strategy" \
    --lookback-points "$STRATEGY_LOOKBACK_POINTS" \
    --source "cron.strategy.$strategy"
}

run_hourly() {
  if [[ "$DISABLE_LEGACY_HOURLY" != "0" ]]; then
    echo "[info] legacy hourly pipeline disabled; use tick schedule instead" >&2
    run_tick
    return 0
  fi

  local -a symbol_args=()
  while IFS= read -r item; do
    [[ -n "$item" ]] || continue
    symbol_args+=("$item")
  done < <(build_symbol_args)

  if ((${#symbol_args[@]})); then
    "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" fetch-market \
      --source "$MARKET_SOURCE" \
      --api-root "$MARKET_API_ROOT" \
      "${symbol_args[@]}"
  else
    "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" fetch-market \
      --source "$MARKET_SOURCE" \
      --api-root "$MARKET_API_ROOT"
  fi

  "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" run-signals \
    --report-log "$REPORT_LOG" \
    --source cron.hourly

  local hour
  hour="$(date +%H)"

  if [[ "$RUN_DS_SHADOW" != "0" ]]; then
    local ds_every
    ds_every="${DS_SHADOW_EVERY_HOURS:-1}"
    if (( ds_every < 1 )); then
      ds_every=1
    fi
    if ((10#$hour % ds_every == 0)); then
      if ! "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" --report-log "$REPORT_LOG" ds-shadow-run \
        --source cron.ds-shadow; then
        echo "[warn] ds-shadow-run failed; continue execute-sim pipeline" >&2
      fi
    fi
  fi

  if [[ "$RUN_EXECUTE_SIM" != "0" ]]; then
    local -a execute_args=(
      --state-dir "$STATE_DIR"
      --report-log "$REPORT_LOG"
      execute-sim
      --source cron.execute
      --lookback-points "$EXECUTE_LOOKBACK_POINTS"
    )
    if [[ "$EXECUTE_SIM_NOTIFY" != "0" ]]; then
      execute_args+=(--notify)
    fi
    "$PYTHON_BIN" -m sim_trading "${execute_args[@]}"
  fi

  if ((10#$hour % 3 == 0)); then
    "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" emit-status-report \
      --report-log "$REPORT_LOG" \
      --source cron.3hourly
  fi

  if [[ "$RUN_VALIDATE_STRATEGY" != "0" ]]; then
    local validate_every
    validate_every="${VALIDATE_EVERY_HOURS:-6}"
    if (( validate_every < 1 )); then
      validate_every=6
    fi
    if ((10#$hour % validate_every == 0)); then
      local -a validate_args=(
        --state-dir "$STATE_DIR"
        --report-log "$REPORT_LOG"
        validate-strategy
        --source cron.validate
      )
      if [[ -n "$VALIDATE_LOOKBACK_POINTS" ]]; then
        validate_args+=(--lookback-points "$VALIDATE_LOOKBACK_POINTS")
      fi
      if [[ -n "$VALIDATE_STEP_POINTS" ]]; then
        validate_args+=(--step-points "$VALIDATE_STEP_POINTS")
      fi
      "$PYTHON_BIN" -m sim_trading "${validate_args[@]}"
    fi
  fi
}

run_tick() {
  if (( UNIVERSE_REFRESH_EVERY_MINUTES < 1 )); then
    UNIVERSE_REFRESH_EVERY_MINUTES=15
  fi
  if (( BASELINE_STRATEGY_EVERY_MINUTES < 1 )); then
    BASELINE_STRATEGY_EVERY_MINUTES=30
  fi
  if (( DS_CONSERVATIVE_STRATEGY_EVERY_MINUTES < 1 )); then
    DS_CONSERVATIVE_STRATEGY_EVERY_MINUTES=30
  fi
  if (( DS_AGGRESSIVE_STRATEGY_EVERY_MINUTES < 1 )); then
    DS_AGGRESSIVE_STRATEGY_EVERY_MINUTES=30
  fi

  if [[ "$RUN_UNIVERSE_REFRESH" != "0" ]] && should_run_interval universe "$UNIVERSE_REFRESH_EVERY_MINUTES"; then
    "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" --report-log "$REPORT_LOG" universe-refresh \
      --api-root "$UNIVERSE_API_ROOT" \
      --source binance
    mark_interval_run universe
  fi

  if [[ "$RUN_BASELINE_STRATEGY" != "0" ]] && should_run_interval strategy-baseline "$BASELINE_STRATEGY_EVERY_MINUTES"; then
    run_strategy_track baseline
    mark_interval_run strategy-baseline
  fi

  if [[ "$RUN_DS_CONSERVATIVE_STRATEGY" != "0" ]] && should_run_interval strategy-ds-conservative "$DS_CONSERVATIVE_STRATEGY_EVERY_MINUTES"; then
    run_strategy_track ds_conservative
    mark_interval_run strategy-ds-conservative
  fi

  if [[ "$RUN_DS_AGGRESSIVE_STRATEGY" != "0" ]] && should_run_interval strategy-ds-aggressive "$DS_AGGRESSIVE_STRATEGY_EVERY_MINUTES"; then
    run_strategy_track ds_aggressive
    mark_interval_run strategy-ds-aggressive
  fi

  if should_run_interval report 180; then
    "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" emit-status-report \
      --report-log "$REPORT_LOG" \
      --source cron.3hourly
    mark_interval_run report
  fi
}

run_daily() {
  local report_day
  report_day="${1:-$(date +%F)}"

  SIM_TRADING_AUTO_REPORT=0 "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" report \
    --date "$report_day" \
    --output "$REPORTS_DIR/$report_day.md"

  "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" notify-task \
    --report-log "$REPORT_LOG" \
    --task daily-summary \
    --status ok \
    --did-what "Generated markdown report for $report_day at $REPORTS_DIR/$report_day.md." \
    --risk "Reporting only. No portfolio state changed." \
    --next "Review the daily report and keep hourly status reports running." \
    --source cron.daily
}

case "${1:-hourly}" in
  tick)
    run_tick
    ;;
  hourly)
    run_hourly
    ;;
  daily)
    run_daily "${2:-}"
    ;;
  *)
    echo "usage: $0 [tick|hourly|daily] [YYYY-MM-DD]" >&2
    exit 1
    ;;
esac
