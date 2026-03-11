#!/usr/bin/env bash
set -euo pipefail

PAYLOAD="${SIM_TRADING_REPORT_PAYLOAD:-}"
CHANNEL="${SIM_TRADING_NOTIFY_CHANNEL:-telegram}"
TARGET="${SIM_TRADING_NOTIFY_TELEGRAM_TARGET:-6330259978}"

if [[ -z "$PAYLOAD" ]]; then
  exit 0
fi

MESSAGE="$(python3 - <<'PY'
import json,os
p=json.loads(os.environ.get('SIM_TRADING_REPORT_PAYLOAD','{}'))
print(
    "【sim-trading主动汇报】\n"
    f"做了啥: {p.get('did_what','')}\n"
    f"当前状态: {p.get('current_status',p.get('status',''))} ({p.get('task','')})\n"
    f"风险影响: {p.get('risk_impact','')}\n"
    f"下一步: {p.get('next_step','')}\n"
    f"来源: {p.get('source','')}"
)
PY
)"

openclaw message send --channel "$CHANNEL" --target "$TARGET" --message "$MESSAGE" >/dev/null 2>&1 || true
