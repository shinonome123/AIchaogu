# Refactor Log

## Modules created

- `pyproject.toml`: package metadata and console entrypoints.
- `sim_trading/__init__.py`, `sim_trading/__main__.py`: package version and module launcher.
- `sim_trading/models.py`: shared dataclasses and decimal helpers.
- `sim_trading/storage.py`: JSON/CSV persistence helpers and runtime file paths.
- `sim_trading/ledger.py`: initialization, trade recording, positions, and equity snapshots.
- `sim_trading/risk.py`: position cap, daily loss cap, and stop-loss checks.
- `sim_trading/strategy.py`: strategy interface and example equal-weight momentum strategy.
- `sim_trading/report.py`: markdown daily reporting.
- `sim_trading/cli.py`: CLI command wiring.
- `scripts/*.py`: thin wrappers for init, trade, snapshot, status, and report commands.
- `seeds/initial_state.json`: machine-readable seed migrated from markdown context.

## Data schema

- `account.json`
  - `account_id`, `base_currency`, `cash_balance`, `realized_pnl_total`
  - `created_at`, `updated_at`, `source_note`, `metadata`
- `config.json`
  - `risk.max_position_size_pct`
  - `risk.daily_loss_cap_pct`
  - `risk.default_stop_loss_pct`
  - `risk.require_stop_loss`
  - `strategy.name`, `strategy.notes`
  - `seed_source_path`, `seed_source_note`
- `positions.json`
  - `symbol`, `quantity`, `average_entry_price`, `last_price`
  - `stop_loss`, `opened_at`, `updated_at`, `metadata`
- `market_prices.json`
  - per-symbol `price`, `timestamp`
- `trades.csv`
  - `trade_id`, `timestamp`, `symbol`, `side`, `quantity`, `price`, `notional`, `fee`
  - `strategy`, `note`, `stop_loss`, `realized_pnl`
  - `cash_after`, `position_qty_after`, `nav_after`
- `equity_curve.csv`
  - `timestamp`, `cash_balance`, `positions_market_value`, `nav`
  - `realized_pnl_total`, `unrealized_pnl_total`, `drawdown_pct`
  - `breached_stop_losses`, `marks_json`

## Risk rules

- Max position size: default `40%` of current NAV at the proposed fill price.
- Daily loss cap: blocks new trades once current NAV is down `10%` or more from the first persisted snapshot of the day.
- Stop-loss handling:
  - required on buys by default
  - explicit stop-loss must be below buy price
  - if omitted, v1 derives one from `default_stop_loss_pct` (`5%`)
  - breach detection is alert-only and appears in status/report output
- Long-only enforcement: sell orders cannot exceed the current long quantity.

## Known risks and next steps

- Monetary math still uses serialized decimals in JSON/CSV but does not yet enforce exchange-style precision per symbol.
- Seed migration is synthetic because the source markdown did not provide actual quantities or fill prices.
- Historical reports depend on the persisted equity curve plus current materialized positions; full event-sourced replay is not implemented yet.
- No concurrency control; simultaneous writers could race on the JSON state files.
- No test suite yet; current verification is command-level.
- Trial-readiness next steps:
  - add unit and CLI integration tests
  - introduce per-symbol precision, fees, and slippage models
  - persist order intents separately from fills
  - add audit log hashing / immutable event storage
  - add strategy scheduling, signal ingestion, and alerting hooks
  - replace local files with transactional storage before any real-money pilot
