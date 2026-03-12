# Sim Trading v2

Simulation-only trading ledger and ops toolkit with local JSON/CSV state, a guarded dashboard/webhook pair, a simulated execution engine, hard execution-time risk gates, and walk-forward validation.

## What is included

- `sim_trading/ledger.py`: cash, positions, trades, and equity snapshots.
- `sim_trading/market.py`: public market fetcher, market-feed cache, and signal snapshot runner.
- `sim_trading/universe.py`: Binance spot USDT universe builder, Top 120 / Top 30 shortlist artifacts, and audit log.
- `sim_trading/execution.py`: target-to-order simulation engine with append-only order lifecycle, slippage, fees, and hard risk rejections.
- `sim_trading/strategy_tracks.py`: isolated baseline / ds_conservative / ds_aggressive ledgers and comparison metrics.
- `sim_trading/validation.py`: walk-forward validation runner built on the same execution path.
- `sim_trading/notifier.py`: standardized task/status payloads and JSONL notification logging.
- `sim_trading/servers.py`: stdlib webhook, dashboard, auth gate, and health endpoint.
- `sim_trading/cli.py`: Phase1/Phase2 commands plus `universe-refresh`, `strategy-run`, and `strategy-compare`.

## Runtime state

The state directory now includes:

- `account.json`
- `config.json`
- `positions.json`
- `market_prices.json`
- `market_feed.jsonl`
- `universe_all.json`
- `universe_filtered.json`
- `universe_top120.json`
- `universe_top30.json`
- `universe_runs.jsonl`
- `signal_runs.jsonl`
- `ds_requests.jsonl`
- `ds_decisions.jsonl`
- `ds_rejections.jsonl`
- `ds_approvals.jsonl`
- `order_events.jsonl`
- `execution_runs.jsonl`
- `risk_state.json`
- `risk_events.jsonl`
- `validation_runs.jsonl`
- `position_normalizations.jsonl`
- `trades.csv`
- `equity_curve.csv`
- `strategies/<name>/...` for `baseline`, `ds_conservative`, and `ds_aggressive`

The notification log still defaults to the sibling of the state directory, so `demo/state` writes to `demo/reports-log.jsonl`.

## Quick start

Initialize the sample state:

```bash
python3 -m sim_trading --state-dir demo/state init --seed-file seeds/initial_state.json
```

Fetch prices and build a signal snapshot:

```bash
python3 -m sim_trading --state-dir demo/state fetch-market \
  --symbol BTC/USDT \
  --symbol ETH/USDT \
  --symbol SOL/USDT

python3 -m sim_trading --state-dir demo/state run-signals \
  --report-log demo/reports-log.jsonl \
  --lookback-points 6 \
  --notify
```

Refresh the Binance spot USDT universe and generate the Top 120 / Top 30 shortlists:

```bash
python3 -m sim_trading --state-dir demo/state universe-refresh \
  --report-log demo/reports-log.jsonl
```

Ranking rule for the shortlist:

- sort descending by composite `rank_score` (volume + trade_count + spread quality + listing_age)
- then descending by `quoteVolume`
- then descending by `tradeCount`
- then ascending by quoted spread
- then descending by listing age
- then symbol

You can tune universe filters from CLI, for example:

```bash
python3 -m sim_trading --state-dir demo/state universe-refresh \
  --min-listing-age-days 45 \
  --min-quote-volume 10000000 \
  --min-trade-count 5000 \
  --max-spread-pct 0.006
```

Run the isolated strategy tracks:

```bash
python3 -m sim_trading --state-dir demo/state strategy-run --strategy baseline
python3 -m sim_trading --state-dir demo/state strategy-run --strategy ds_conservative
python3 -m sim_trading --state-dir demo/state strategy-run --strategy ds_aggressive

python3 -m sim_trading --state-dir demo/state strategy-compare --output-json
```

Available rule-based strategy engines for signal snapshots:

- `equal_weight_momentum` (default)
- `mean_reversion`
- `breakout_momentum`
- `tiered_momentum` (rank-decay allocation for trend leaders)

Set strategy engine in `state/config.json` under `strategy.name`.

Defaults for the triple-strategy framework:

- starting capital: `100 USDT` per strategy
- max position per symbol: `8%`
- max gross exposure: `60%`
- max concurrent positions: `10`
- default stop loss: `3.5%`
- cooldown: `3` consecutive losing cycles -> `3` blocked cycles
- daily loss breaker: `baseline -3.0%`, `ds_conservative -2.5%`, `ds_aggressive -4.0%`

Normalize legacy synthetic seed holdings after prices are available:

```bash
python3 -m sim_trading --state-dir demo/state normalize-positions \
  --report-log demo/reports-log.jsonl \
  --timestamp 2026-03-11T18:05:00+08:00
```

Run one simulated execution cycle:

```bash
python3 -m sim_trading --state-dir demo/state execute-sim \
  --report-log demo/reports-log.jsonl \
  --lookback-points 6 \
  --notify

# optional: make the root portfolio follow one strategy track
python3 -m sim_trading --state-dir demo/state strategy-selection set --strategy baseline
python3 -m sim_trading --state-dir demo/state execute-sim \
  --decision-source strategy-selected \
  --lookback-points 6
```

The execution engine converts target weights into simulated orders and fills, writes append-only lifecycle events to `state/order_events.jsonl`, summarizes each cycle in `state/execution_runs.jsonl`, and applies configured slippage plus fees.

## DeepSeek operator mode

Stage A shadow mode logs DS trade intentions without executing them:

```bash
export SIM_TRADING_DEEPSEEK_ENABLED=1
export SIM_TRADING_DEEPSEEK_API_KEY=...
export SIM_TRADING_DEEPSEEK_BASE_URL=https://api.deepseek.com
export SIM_TRADING_DEEPSEEK_MODEL=deepseek-chat

python3 -m sim_trading --state-dir demo/state ds-shadow-run \
  --report-log demo/reports-log.jsonl
```

Stage B approval mode lets the operator approve the latest validated DS plan for exactly one simulated execution cycle:

```bash
python3 -m sim_trading --state-dir demo/state ds-approve-latest \
  --report-log demo/reports-log.jsonl

python3 -m sim_trading --state-dir demo/state execute-sim \
  --report-log demo/reports-log.jsonl \
  --decision-source ds-approved
```

Audit files:

- `state/ds_requests.jsonl`: prompt and request metadata only, never the API key
- `state/ds_decisions.jsonl`: validated DS payloads plus execution previews
- `state/ds_rejections.jsonl`: API, schema, or conversion failures
- `state/ds_approvals.jsonl`: manual approvals and approval-consumed records

`ds-shadow-run` is a graceful no-op when `SIM_TRADING_DEEPSEEK_ENABLED=0` or the API key is missing, and it records the reason for auditability.

Inspect or toggle hard-risk gates:

```bash
python3 -m sim_trading --state-dir demo/state risk-status
python3 -m sim_trading --state-dir demo/state risk-check
python3 -m sim_trading --state-dir demo/state risk-status \
  --kill-switch on \
  --reason "manual freeze"
```

Run walk-forward validation across historical market-feed snapshots:

```bash
python3 -m sim_trading --state-dir demo/state validate-strategy \
  --report-log demo/reports-log.jsonl \
  --lookback-points 4 \
  --step-points 1
```

Validation summaries are appended to `state/validation_runs.jsonl` with return, max drawdown, win rate, profit factor, and longest losing streak.

## Dashboard and API

The dashboard exposes:

- `/`
- `/api/status`
- `/api/strategy?name=baseline|ds_conservative|ds_aggressive`
- `/api/experiments/latest`
- `/api/experiments/history?n=20`
- `/api/health`

The web UI defaults to Chinese. Append `?lang=en` or switch the selector in the header for English. Append `?view=overview`, `?view=baseline`, `?view=ds_conservative`, or `?view=ds_aggressive` to open a specific workspace tab directly.

Navigation behavior:

- `Overview` is the default tab and shows the root portfolio NAV curve, open positions, and cross-strategy comparison.
- `baseline`, `ds_conservative`, and `ds_aggressive` each open a dedicated strategy panel with NAV, return, drawdown, risk-trigger count, positions summary, recent trades, and recent events.
- The right-side ops panels follow the active workspace tab, so execution, risk, validation, and DS summaries stay aligned with the selected strategy.

`/api/status` now includes:

- normalization state (`position_mode`, `position_mode_is_normalized`, pending symbols)
- latest execution summary (`latest_execution_run`)
- hard-risk gate state and the last circuit-breaker event (`risk_status`, `last_circuit_breaker_event`)
- latest validation summary (`latest_validation_run`)
- latest experiment evaluation run plus a compact history (`latest_experiment_run`, `experiment_history`)
- DS operator summaries (`ds_mode`, `latest_ds_decision`, `latest_ds_rejection`, `latest_ds_approval`)
- universe status (`universe_status`)
- cross-strategy metrics (`strategy_compare`)
- strategy workspace metadata (`strategy_tabs`, `default_strategy_view`)
- `timeseries.equity_curve`
- `timeseries.market_prices` keyed by currently held symbol

`/api/strategy?name=...` returns one strategy detail payload with:

- summary metrics (`nav`, `return_pct`, current/max drawdown, risk-trigger count, turnover, win rate, profit factor)
- latest execution / validation / risk / DS context
- positions summary plus full position rows
- recent trades and recent events
- strategy-local `timeseries.equity_curve` and held-symbol `timeseries.market_prices`

The dashboard renders:

- a denser three-column layout with compact top cards, a center strategy workspace, and side rails for market + ops detail
- an `Overview / baseline / ds_conservative / ds_aggressive` strategy switcher
- root NAV / equity curve from `equity_curve.csv`
- strategy-local NAV curves from `state/strategies/<name>/equity_curve.csv`
- held-asset price trend cards from `market_feed.jsonl` for the active workspace context
- execution, risk, validation, and DS panels that stay available without removing the existing feature set
- a universe panel with all / filtered / Top 120 / Top 30 counts and the latest refresh timestamp
- a strategy comparison panel with return, max drawdown, win rate, profit factor, turnover, and risk-trigger count
- strategy comparison now also includes a recommended allocation weight per track plus a lead-strategy hint derived from risk-adjusted scoring

## Security and ops

Rotate secrets into `.ops.env` without printing full values:

```bash
python3 -m sim_trading rotate-tokens --ops-env .ops.env
```

Optional dashboard auth is controlled by env vars in `.ops.env`:

```bash
SIM_TRADING_DASHBOARD_BEARER_TOKEN=...
SIM_TRADING_DASHBOARD_BASIC_USER=ops
SIM_TRADING_DASHBOARD_BASIC_PASS=...
```

The webhook still requires a shared token and supports replay protection:

```bash
SIM_TRADING_WEBHOOK_TOKEN=...
SIM_TRADING_WEBHOOK_REPLAY_TTL_SECONDS=300
```

Start the guarded services with repo-local PID and log files:

```bash
./scripts/ops_start.sh
./scripts/ops_status.sh
./scripts/ops_restart.sh
```

## Automated loop

Hourly cron helper:

```bash
./scripts/cron_phase1.sh hourly
./scripts/cron_phase1.sh daily 2026-03-11
```

15-minute framework tick:

```bash
./scripts/cron_phase1.sh tick
```

The hourly helper now runs:

1. `fetch-market`
2. `run-signals --notify`
3. optional `ds-shadow-run`
4. `execute-sim`
5. `emit-status-report`
6. optional `validate-strategy`

The new `tick` flow keeps the existing 3-hour report cadence and adds:

1. `universe-refresh` every 15 minutes
2. `fetch-market` every 60 seconds (configurable)
3. `strategy-run --strategy baseline` every 30 minutes
4. `strategy-run --strategy ds_conservative` every 30 minutes
5. `strategy-run --strategy ds_aggressive` every 30 minutes
6. `emit-status-report` every 3 hours

Useful overrides:

- `MARKET_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT` (example override, fully customizable)
- `MARKET_SOURCE=binance`
- `MARKET_API_ROOT=https://api.binance.com`
- `UNIVERSE_API_ROOT=https://api.binance.com`
- `RUN_UNIVERSE_REFRESH=1`
- `UNIVERSE_REFRESH_EVERY_MINUTES=15`
- `RUN_FETCH_MARKET=1`
- `FETCH_MARKET_EVERY_SECONDS=60`
- `RUN_BASELINE_STRATEGY=1`
- `RUN_DS_CONSERVATIVE_STRATEGY=1`
- `RUN_DS_AGGRESSIVE_STRATEGY=1`
- `STRATEGY_RUN_EVERY_MINUTES=30`
- `STRATEGY_LOOKBACK_POINTS=6`
- `RUN_DS_SHADOW=1`
- `DS_SHADOW_EVERY_HOURS=1`
- `RUN_EXECUTE_SIM=0` to keep the old fetch/signals-only loop
- `RUN_VALIDATE_STRATEGY=1`
- `VALIDATE_EVERY_HOURS=6`

## Health checks

Validate state files, PID files, and report freshness:

```bash
python3 -m sim_trading --state-dir demo/state health-check \
  --report-log demo/reports-log.jsonl \
  --dashboard-pid-file .ops/run/dashboard.pid \
  --webhook-pid-file .ops/run/webhook.pid \
  --dashboard-health-url http://127.0.0.1:8780/api/health \
  --webhook-host 127.0.0.1 \
  --webhook-port 8765
```

## Demo assets

- `demo/state/order_events.jsonl`: sample order lifecycle history.
- `demo/state/execution_runs.jsonl`: sample execution summaries.
- `demo/state/risk_state.json`: current hard-risk gate state.
- `demo/state/risk_events.jsonl`: sample risk rejections and kill-switch events.
- `demo/state/validation_runs.jsonl`: sample walk-forward validation output.
- `demo/reports/2026-03-11.md`: sample markdown report after Phase2 execution and risk events.
- `demo/state/universe_top30.json`: sample DS candidate subset.
- `demo/state/strategies/`: sample isolated ledgers for all three strategy tracks.
- `demo/strategy_compare.json`: sample comparison payload.

## Verification

Run the included verification scripts:

```bash
python3 scripts/verify_ops_http.py
python3 scripts/verify_dashboard_payload.py
python3 scripts/verify_automation_flow.py
python3 scripts/verify_phase2_state.py
python3 scripts/verify_ds_operator.py
python3 scripts/verify_universe_triple_strategy.py
```

See `OPS_GUIDE.md` for deployment flow and `SECURITY_NOTES.md` for threat model, including DS hallucination and approval-path safety notes.
