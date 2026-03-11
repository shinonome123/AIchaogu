#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <task> <status> <did_what> [risk_impact] [next_step] [source]" >&2
  exit 1
fi

WEBHOOK_URL="${WEBHOOK_URL:-http://127.0.0.1:8765/task-done}"
TOKEN="${SIM_TRADING_WEBHOOK_TOKEN:?SIM_TRADING_WEBHOOK_TOKEN is required}"

TASK="$1"
STATUS="$2"
DID_WHAT="$3"
RISK_IMPACT="${4:-No direct portfolio change.}"
NEXT_STEP="${5:-Inspect the dashboard and continue monitoring.}"
SOURCE="${6:-external.process}"

PAYLOAD="$(
  python3 - "$TASK" "$STATUS" "$DID_WHAT" "$RISK_IMPACT" "$NEXT_STEP" "$SOURCE" "$TOKEN" <<'PY'
import json
import sys
from datetime import datetime
from uuid import uuid4

task, status, did_what, risk_impact, next_step, source, token = sys.argv[1:]
timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
nonce = f"{task}-{uuid4().hex}"
print(
    json.dumps(
        {
            "task": task,
            "status": status,
            "did_what": did_what,
            "risk_impact": risk_impact,
            "next_step": next_step,
            "source": source,
            "token": token,
            "timestamp": timestamp,
            "nonce": nonce,
        }
    )
)
PY
)"

curl -fsS \
  -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  --data "$PAYLOAD"
