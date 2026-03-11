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
MARKET_SOURCE="${MARKET_SOURCE:-binance}"
MARKET_API_ROOT="${MARKET_API_ROOT:-https://api.binance.com}"
RUN_DIR="${SIM_TRADING_RUN_DIR:-$ROOT/.ops/run}"
LOG_DIR="${SIM_TRADING_LOG_DIR:-$ROOT/.ops/logs}"
LOCK_DIR="$RUN_DIR/held-fast.lock"
ERR_LOG="$LOG_DIR/held-fast.err.log"

mkdir -p "$RUN_DIR" "$LOG_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

held_symbols_raw="$($PYTHON_BIN - "$STATE_DIR" <<'PY'
import json
import sys
from decimal import Decimal
from pathlib import Path

state_dir = Path(sys.argv[1])
positions_path = state_dir / "positions.json"
if not positions_path.exists():
    raise SystemExit(0)

try:
    payload = json.loads(positions_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

iterable: list[tuple[str, dict]] = []
if isinstance(payload, dict):
    for symbol, row in payload.items():
        if isinstance(row, dict):
            iterable.append((str(symbol), row))
elif isinstance(payload, list):
    for row in payload:
        if not isinstance(row, dict):
            continue
        iterable.append((str(row.get("symbol", "")), row))
else:
    raise SystemExit(0)

seen = set()
for symbol, row in sorted(iterable, key=lambda item: item[0]):
    normalized = symbol.strip().upper()
    if not normalized or normalized in seen:
        continue
    try:
        quantity = Decimal(str(row.get("quantity", "0")))
    except Exception:
        continue
    if quantity > 0:
        print(normalized)
        seen.add(normalized)
PY
)"

symbol_args=()
while IFS= read -r symbol; do
  [[ -n "$symbol" ]] || continue
  symbol_args+=(--symbol "$symbol")
done <<< "$held_symbols_raw"

if (( ${#symbol_args[@]} == 0 )); then
  exit 0
fi

if ! "$PYTHON_BIN" -m sim_trading --state-dir "$STATE_DIR" fetch-market \
  --source "$MARKET_SOURCE" \
  --api-root "$MARKET_API_ROOT" \
  --prices-only \
  "${symbol_args[@]}" \
  >/dev/null 2>>"$ERR_LOG"; then
  echo "[$(date -Iseconds)] held-fast fetch failed" >>"$ERR_LOG"
fi
