#!/usr/bin/env bash
set -euo pipefail
cd /Users/shinonome/clawd/sim-trading
set -a
source ./.ops.env
set +a
./scripts/cron_phase1.sh tick >> /Users/shinonome/clawd/sim-trading/.ops/logs/cron-tick.log 2>&1
