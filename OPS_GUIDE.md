# Ops Guide

## 1. Prepare `.ops.env`

Create or rotate secrets:

```bash
python3 -m sim_trading rotate-tokens --ops-env .ops.env
```

Typical `.ops.env` values:

```bash
SIM_TRADING_STATE_DIR=demo/state
SIM_TRADING_REPORT_LOG=demo/reports-log.jsonl
SIM_TRADING_DASHBOARD_HOST=127.0.0.1
SIM_TRADING_DASHBOARD_PORT=8780
SIM_TRADING_WEBHOOK_HOST=127.0.0.1
SIM_TRADING_WEBHOOK_PORT=8765
SIM_TRADING_WEBHOOK_REPLAY_TTL_SECONDS=300
SIM_TRADING_DASHBOARD_BEARER_TOKEN=...
SIM_TRADING_DASHBOARD_BASIC_USER=ops
SIM_TRADING_DASHBOARD_BASIC_PASS=...
SIM_TRADING_WEBHOOK_TOKEN=...
SIM_TRADING_DEEPSEEK_ENABLED=0
SIM_TRADING_DEEPSEEK_API_KEY=...
SIM_TRADING_DEEPSEEK_BASE_URL=https://api.deepseek.com
SIM_TRADING_DEEPSEEK_MODEL=deepseek-chat
SIM_TRADING_NOTIFY_HOOK=openclaw system event --text "$SIM_TRADING_REPORT_PAYLOAD" --mode now
```

## 2. Start the services

Guarded startup:

```bash
./scripts/ops_start.sh
```

This creates:

- `.ops/run/dashboard.pid`
- `.ops/run/webhook.pid`
- `.ops/logs/dashboard.log`
- `.ops/logs/webhook.log`

Status and restart:

```bash
./scripts/ops_status.sh
./scripts/ops_restart.sh
```

## 3. Service endpoints

Dashboard:

- `/`: HTML panel, default Chinese UI with `?lang=en` support and direct workspace navigation via `?view=overview|baseline|ds_conservative|ds_aggressive`
- `/api/status`: live snapshot, normalization metadata, execution summary, risk gate state, validation summary, DS operator summaries, recent notifications, and `strategy_tabs`
- `/api/strategy?name=baseline|ds_conservative|ds_aggressive`: one strategy detail payload for the active workspace tab
- `/api/experiments/latest`: latest walk-forward experiment payload with gate status
- `/api/experiments/history?n=20`: recent experiment timeline for dashboard drilldown
- `/api/health`: read-only health payload

Webhook:

- `POST /task-done`

## 4. Auth and replay protection

Dashboard auth supports either:

- `Authorization: Bearer <token>`
- `Authorization: Basic <base64(user:pass)>`

When a browser first opens `/` with a bearer token, the server sets a same-origin cookie so the page can continue refreshing `/api/status` and `/api/strategy`.

Webhook protections:

- shared token match remains required
- replay protection is enabled when `SIM_TRADING_WEBHOOK_REPLAY_TTL_SECONDS > 0`
- requests must include `timestamp` and `nonce` when replay protection is enabled

## 5. Universe and strategy framework

Refresh the Binance spot USDT universe:

```bash
python3 -m sim_trading --state-dir demo/state universe-refresh \
  --report-log demo/reports-log.jsonl
```

Filtering rules:

- start from all Binance spot `*USDT` symbols
- exclude leveraged-token suffixes `UP`, `DOWN`, `BULL`, `BEAR`
- exclude obvious stable-stable pairs such as `USDC/USDT`
- exclude listing age under `60` days
- require `quoteVolume >= 20,000,000`
- require `tradeCount >= 10,000`
- require spread `<= 0.30%`

Ranking rule:

- `quoteVolume` descending
- `tradeCount` descending
- spread ascending
- listing age descending
- symbol ascending

Artifacts written under state:

- `universe_all.json`
- `universe_filtered.json`
- `universe_top120.json`
- `universe_top30.json`
- `universe_runs.jsonl`

Run the isolated strategy tracks:

```bash
python3 -m sim_trading --state-dir demo/state strategy-run --strategy baseline
python3 -m sim_trading --state-dir demo/state strategy-run --strategy ds_conservative
python3 -m sim_trading --state-dir demo/state strategy-run --strategy ds_aggressive
python3 -m sim_trading --state-dir demo/state strategy-compare --output-json

# optional: route root execute-sim decisions from one selected strategy track
python3 -m sim_trading --state-dir demo/state strategy-selection set --strategy baseline
python3 -m sim_trading --state-dir demo/state execute-sim --decision-source strategy-selected
```

Strategy state directories live under `state/strategies/<name>/`.

Risk defaults for all three tracks:

- `max_position_size_pct = 0.08`
- `max_gross_exposure_pct = 0.60`
- `max_concurrent_positions = 10`
- `default_stop_loss_pct = 0.035`
- `consecutive_loss_limit = 3`
- `loss_cooldown_cycles = 3`

Daily loss breakers:

- `baseline = -3.0%`
- `ds_conservative = -2.5%`
- `ds_aggressive = -4.0%`

## 6. Automation cadence

The hourly helper still preserves the 3-hour status-report cadence and now optionally runs DS shadow mode, Phase2 execution, and validation:

1. `fetch-market`
2. `run-signals --notify`
3. optional `ds-shadow-run`
4. `execute-sim`
5. `emit-status-report` every 3 hours
6. optional `validate-strategy`

Run manually:

```bash
./scripts/cron_phase1.sh hourly
./scripts/cron_phase1.sh daily 2026-03-11
```

New 15-minute strategy-framework tick:

```bash
./scripts/cron_phase1.sh tick
```

`tick` does:

1. `universe-refresh` every 15 minutes
2. `strategy-run --strategy baseline` every 30 minutes
3. `strategy-run --strategy ds_conservative` every 30 minutes
4. `strategy-run --strategy ds_aggressive` every 30 minutes
5. `emit-status-report` every 3 hours

Useful env overrides:

- `RUN_UNIVERSE_REFRESH=1`
- `UNIVERSE_REFRESH_EVERY_MINUTES=15`
- `UNIVERSE_API_ROOT=https://api.binance.com`
- `RUN_BASELINE_STRATEGY=1`
- `RUN_DS_CONSERVATIVE_STRATEGY=1`
- `RUN_DS_AGGRESSIVE_STRATEGY=1`
- `STRATEGY_RUN_EVERY_MINUTES=30`
- `STRATEGY_LOOKBACK_POINTS=6`
- `RUN_DS_SHADOW=1` to enable hourly DeepSeek shadow runs
- `DS_SHADOW_EVERY_HOURS=1`
- `RUN_EXECUTE_SIM=0` to disable execution while keeping the old fetch/signals loop
- `EXECUTE_SIM_NOTIFY=1` to emit explicit risk-rejection notifications from cron execution
- `EXECUTE_LOOKBACK_POINTS=6`
- `RUN_VALIDATE_STRATEGY=1`
- `VALIDATE_EVERY_HOURS=6`
- `VALIDATE_LOOKBACK_POINTS=4`
- `VALIDATE_STEP_POINTS=1`
- `MARKET_SYMBOLS`
- `MARKET_SOURCE`
- `MARKET_API_ROOT`
- `PYTHON_BIN`

## 7. DeepSeek operator workflow

Shadow mode:

```bash
python3 -m sim_trading --state-dir demo/state ds-shadow-run \
  --report-log demo/reports-log.jsonl
```

Approval mode:

```bash
python3 -m sim_trading --state-dir demo/state ds-approve-latest \
  --report-log demo/reports-log.jsonl

python3 -m sim_trading --state-dir demo/state execute-sim \
  --report-log demo/reports-log.jsonl \
  --decision-source ds-approved
```

Audit files:

- `state/ds_requests.jsonl`
- `state/ds_decisions.jsonl`
- `state/ds_rejections.jsonl`
- `state/ds_approvals.jsonl`

The dashboard exposes:

- `ds_mode`: `disabled`, `shadow`, or `approval`
- `latest_ds_decision`
- `latest_ds_rejection`
- `latest_ds_approval`

Strategy workspace usage:

- Default landing tab is `Overview`, which keeps the root portfolio NAV curve, current positions, and cross-strategy compare in the center column.
- `baseline`, `ds_conservative`, and `ds_aggressive` each open a dedicated strategy panel with NAV, return, drawdown, risk-trigger count, execution context, DS context if applicable, positions summary, recent trades, and recent events.
- The URL can pin a tab with `?view=baseline`, `?view=ds_conservative`, or `?view=ds_aggressive`.
- `/api/status` exposes `strategy_tabs` for the selector state, while `/api/strategy?name=...` returns the detail payload used by the strategy panels.

The approved plan is consumed once `execute-sim --decision-source ds-approved` succeeds. Existing hard risk gates still decide whether any simulated buy order can pass.

The DS strategy tracks reuse the same DS client but keep independent ledgers. `ds_conservative` asks for a cautious bias; `ds_aggressive` asks for a normal bias. Both still pass through the same hard risk gates.

## 8. Hard risk controls

Phase2 introduces execution-time blocking, not just alerts:

- max position weight per symbol
- daily loss circuit breaker
- consecutive-loss cooldown
- global kill switch

Inspect the current state:

```bash
python3 -m sim_trading --state-dir demo/state risk-status
python3 -m sim_trading --state-dir demo/state risk-check
```

Toggle the kill switch:

```bash
python3 -m sim_trading --state-dir demo/state risk-status \
  --kill-switch on \
  --reason "manual freeze"
```

Risk records are append-only:

- `state/risk_state.json`
- `state/risk_events.jsonl`

Execution-time order rejections are also recorded in:

- `state/order_events.jsonl`
- `state/execution_runs.jsonl`

## 9. Strategy validation

Run walk-forward validation:

```bash
python3 -m sim_trading --state-dir demo/state validate-strategy \
  --report-log demo/reports-log.jsonl \
  --lookback-points 4 \
  --step-points 1
```

The runner reuses the simulated execution path over historical `market_feed.jsonl` snapshots and appends summaries to `state/validation_runs.jsonl`.

## 10. Health checks

CLI:

```bash
python3 -m sim_trading --state-dir demo/state health-check \
  --report-log demo/reports-log.jsonl \
  --dashboard-pid-file .ops/run/dashboard.pid \
  --webhook-pid-file .ops/run/webhook.pid \
  --dashboard-health-url http://127.0.0.1:8780/api/health \
  --webhook-host 127.0.0.1 \
  --webhook-port 8765
```

The check validates:

- required state files, including `risk_state.json`
- report-log freshness
- dashboard and webhook PID files
- dashboard `/api/health`
- webhook TCP reachability

## 11. Verification and demo outputs

```bash
python3 scripts/verify_phase2_state.py
python3 scripts/verify_ds_operator.py
python3 scripts/verify_dashboard_payload.py
python3 scripts/verify_universe_triple_strategy.py
```

`scripts/verify_dashboard_payload.py` now checks the strategy-tab payload, `/api/strategy?name=...`, and the HTML shell IDs required by the dashboard layout.

To refresh the demo universe artifacts and isolated strategy ledgers:

```bash
python3 scripts/verify_universe_triple_strategy.py --write-demo --demo-dir demo
```

## 12. Failure modes

- Missing dashboard auth: backward-compatible startup, but the server warns because the panel is unauthenticated.
- Missing webhook token env: the webhook responds with `503` until a token is configured.
- DeepSeek disabled or missing API key: `ds-shadow-run` exits cleanly without execution and records a `noop` reason in `ds_rejections.jsonl`.
- DeepSeek schema or conversion failure: the shadow run records the reason in `ds_rejections.jsonl`; only validated plans can be approved.
- Kill switch on: new simulated buy orders are blocked and explicit risk-rejection records are written.
- Consecutive losing executions: cooldown blocks new buys for the configured number of execution cycles.
- Daily loss circuit breaker: new buys are blocked once the configured intraday loss threshold is breached.
- Missing or stale market marks before normalization: `normalize-positions` refuses symbols without reference prices and `/api/status` continues to flag normalization as pending.
- Stale or missing report log: `health-check` and `/api/health` return an alert state.
- Unwritable state or log paths: market fetch, execution, validation, notifications, or status reports fail fast.
- Missing universe artifacts: `strategy-run` fails fast and tells the operator to run `universe-refresh` first.
- DeepSeek disabled for DS tracks: the DS strategy ledger records a `noop` rejection and skips execution for that cycle.
