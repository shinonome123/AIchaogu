from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from sim_trading.execution import SimulationExecutor
from sim_trading.ledger import LedgerService
from sim_trading.market import build_signal_run_entry
from sim_trading.models import decimal_to_str, now_iso, to_decimal
from sim_trading.storage import append_jsonl, read_csv_rows, read_jsonl, read_last_jsonl


@dataclass(frozen=True)
class ValidationRunResult:
    entry: dict[str, Any]


def load_latest_validation_run(state_dir: Path | str) -> dict[str, Any] | None:
    payload = read_last_jsonl(LedgerService(state_dir).paths.validation_runs)
    return payload if isinstance(payload, dict) else None


def _prices_from_feed_row(row: dict[str, Any]) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    raw_prices = row.get("prices", {})
    if not isinstance(raw_prices, dict):
        return prices
    for symbol, payload in raw_prices.items():
        if not isinstance(payload, dict) or "price" not in payload:
            continue
        prices[str(symbol)] = to_decimal(payload["price"])
    return prices


def _longest_losing_streak(rows: list[dict[str, str]]) -> int:
    longest = 0
    current = 0
    for row in rows:
        pnl = to_decimal(row["realized_pnl"])
        if pnl < 0:
            current += 1
            longest = max(longest, current)
        elif pnl > 0:
            current = 0
    return longest


class StrategyValidator:
    def __init__(self, state_dir: Path | str) -> None:
        self.service = LedgerService(state_dir)

    def validate(
        self,
        *,
        timestamp: str | None = None,
        source: str = "cli.validate-strategy",
        lookback_points: int | None = None,
        step_points: int | None = None,
        initial_capital: Decimal | None = None,
    ) -> ValidationRunResult:
        service = self.service
        config_payload = service.load_config_payload()
        validation_config = service.load_validation_config()
        account = service.load_account()
        feed_rows = [
            row
            for row in read_jsonl(service.paths.market_feed)
            if isinstance(row, dict) and isinstance(row.get("prices"), dict)
        ]
        requested_lookback = lookback_points or validation_config.lookback_points
        requested_step = step_points or validation_config.step_points
        if len(feed_rows) < max(validation_config.min_snapshots, requested_lookback + requested_step):
            raise ValueError(
                "not enough market-feed rows for validation: "
                + f"have {len(feed_rows)}, need at least {max(validation_config.min_snapshots, requested_lookback + requested_step)}"
            )

        run_time = timestamp or now_iso()
        starting_capital = initial_capital or validation_config.initial_capital
        validation_id = f"VAL-{uuid4().hex[:12].upper()}"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_state = tmp_root / "state"
            tmp_seed = tmp_root / "seed.json"
            seed_payload = {
                "account": {
                    "account_id": f"{account.account_id}-validation",
                    "base_currency": account.base_currency,
                    "cash_balance": decimal_to_str(starting_capital),
                    "created_at": str(feed_rows[0].get("timestamp", run_time)),
                    "metadata": {"validation_id": validation_id},
                },
                "positions": [],
                "risk": service.load_risk_config().to_dict(),
                "execution": service.load_execution_config().to_dict(),
                "validation": {
                    **validation_config.to_dict(),
                    "initial_capital": decimal_to_str(starting_capital),
                    "lookback_points": requested_lookback,
                    "step_points": requested_step,
                },
                "strategy": config_payload.get("strategy", {}),
                "source_note": "walk-forward validation seed",
                "source_path": str(service.paths.market_feed),
            }
            tmp_seed.write_text(json.dumps(seed_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temp_service = LedgerService(tmp_state)
            temp_service.initialize_from_seed(tmp_seed)
            executor = SimulationExecutor(tmp_state)

            for index in range(requested_lookback - 1, len(feed_rows) - requested_step, requested_step):
                current_row = feed_rows[index]
                next_row = feed_rows[index + requested_step]
                current_timestamp = str(current_row.get("timestamp", run_time))
                next_timestamp = str(next_row.get("timestamp", run_time))
                current_prices = _prices_from_feed_row(current_row)
                next_prices = _prices_from_feed_row(next_row)
                current_snapshot = temp_service.snapshot(
                    timestamp=current_timestamp,
                    persist=True,
                    price_overrides=current_prices or None,
                )
                signal_entry = build_signal_run_entry(
                    config_payload=config_payload,
                    feed_rows=feed_rows[: index + 1],
                    nav=current_snapshot.nav,
                    risk_config=temp_service.load_risk_config(),
                    source="validation.walkforward",
                    lookback_points=requested_lookback,
                    timestamp=current_timestamp,
                )
                executor.execute_cycle(
                    timestamp=next_timestamp,
                    signal_run_entry=signal_entry,
                    source="validation.walkforward",
                    lookback_points=requested_lookback,
                    price_overrides=next_prices or None,
                )

            temp_equity_rows = read_csv_rows(temp_service.paths.equity_curve)
            temp_trade_rows = read_csv_rows(temp_service.paths.trades)
            temp_execution_runs = read_jsonl(temp_service.paths.execution_runs)

        closed_rows = [row for row in temp_trade_rows if to_decimal(row["realized_pnl"]) != 0]
        winners = [to_decimal(row["realized_pnl"]) for row in closed_rows if to_decimal(row["realized_pnl"]) > 0]
        losers = [to_decimal(row["realized_pnl"]) for row in closed_rows if to_decimal(row["realized_pnl"]) < 0]
        gross_profit = sum(winners, Decimal("0"))
        gross_loss_abs = abs(sum(losers, Decimal("0")))
        starting_nav = to_decimal(temp_equity_rows[0]["nav"])
        ending_nav = to_decimal(temp_equity_rows[-1]["nav"])
        return_pct = ((ending_nav / starting_nav) - Decimal("1")) if starting_nav > 0 else Decimal("0")
        max_drawdown_pct = min((to_decimal(row["drawdown_pct"]) for row in temp_equity_rows), default=Decimal("0"))
        win_rate = (Decimal(len(winners)) / Decimal(len(closed_rows))) if closed_rows else Decimal("0")
        profit_factor = "inf" if gross_loss_abs == 0 and gross_profit > 0 else decimal_to_str(
            (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else Decimal("0")
        )
        longest_losing_streak = _longest_losing_streak(closed_rows)
        status = "ok" if return_pct > 0 else ("watch" if return_pct == 0 else "alert")
        entry = {
            "validation_id": validation_id,
            "timestamp": run_time,
            "source": source,
            "status": status,
            "period_start": str(feed_rows[0].get("timestamp", "")),
            "period_end": str(feed_rows[-1].get("timestamp", "")),
            "lookback_points": requested_lookback,
            "step_points": requested_step,
            "starting_capital": decimal_to_str(starting_capital),
            "starting_nav": decimal_to_str(starting_nav),
            "ending_nav": decimal_to_str(ending_nav),
            "return_pct": decimal_to_str(return_pct),
            "max_drawdown_pct": decimal_to_str(max_drawdown_pct),
            "win_rate": decimal_to_str(win_rate),
            "profit_factor": profit_factor,
            "longest_losing_streak": longest_losing_streak,
            "closed_trade_count": len(closed_rows),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "execution_runs": len(temp_execution_runs),
            "summary": (
                f"return={decimal_to_str(return_pct)} "
                + f"max_dd={decimal_to_str(max_drawdown_pct)} "
                + f"win_rate={decimal_to_str(win_rate)} "
                + f"profit_factor={profit_factor}"
            ),
        }
        append_jsonl(service.paths.validation_runs, entry)
        return ValidationRunResult(entry=entry)
