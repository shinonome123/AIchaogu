from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from sim_trading.ledger import LedgerService
from sim_trading.models import decimal_to_str, to_decimal
from sim_trading.storage import append_jsonl, read_jsonl, read_last_jsonl


def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return to_decimal(value)
    except Exception:  # noqa: BLE001
        return default


def _equity_returns(equity_rows: list[dict[str, str]]) -> list[Decimal]:
    returns: list[Decimal] = []
    for index in range(1, len(equity_rows)):
        prev_nav = _safe_decimal(equity_rows[index - 1].get("nav"))
        nav = _safe_decimal(equity_rows[index].get("nav"))
        if prev_nav <= 0:
            continue
        returns.append((nav / prev_nav) - Decimal("1"))
    return returns


def _bars_per_year(equity_rows: list[dict[str, str]]) -> Decimal:
    timestamps: list[datetime] = []
    for row in equity_rows:
        raw = str(row.get("timestamp", "")).strip()
        if not raw:
            continue
        try:
            timestamps.append(datetime.fromisoformat(raw))
        except ValueError:
            continue
    if len(timestamps) < 2:
        return Decimal("365")
    deltas = [
        max(1.0, (timestamps[idx] - timestamps[idx - 1]).total_seconds())
        for idx in range(1, len(timestamps))
        if timestamps[idx] > timestamps[idx - 1]
    ]
    if not deltas:
        return Decimal("365")
    median_delta = Decimal(str(median(deltas)))
    seconds_per_year = Decimal("31536000")
    return max(Decimal("1"), seconds_per_year / median_delta)


def _stddev(values: list[Decimal]) -> Decimal:
    if len(values) < 2:
        return Decimal("0")
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values) - 1)
    return variance.sqrt()


def compute_validation_metrics(
    *,
    equity_rows: list[dict[str, str]],
    return_pct: Decimal,
    max_drawdown_pct: Decimal,
    downside_target: Decimal = Decimal("0"),
) -> dict[str, str]:
    period_returns = _equity_returns(equity_rows)
    if not period_returns:
        zero = decimal_to_str(Decimal("0"))
        return {
            "annualized_return": zero,
            "annualized_volatility": zero,
            "sharpe": zero,
            "sortino": zero,
            "calmar": zero,
            "recovery_time_bars": "0",
        }

    bars_per_year = _bars_per_year(equity_rows)
    periods = Decimal(len(period_returns))
    if periods > 0:
        annualized_return = (Decimal("1") + return_pct) ** (bars_per_year / periods) - Decimal("1")
    else:
        annualized_return = Decimal("0")

    vol = _stddev(period_returns)
    annualized_vol = vol * bars_per_year.sqrt()
    sharpe = annualized_return / annualized_vol if annualized_vol > 0 else Decimal("0")

    downside = [value - downside_target for value in period_returns if value < downside_target]
    downside_dev = _stddev(downside) * bars_per_year.sqrt() if downside else Decimal("0")
    sortino = annualized_return / downside_dev if downside_dev > 0 else Decimal("0")

    calmar = annualized_return / abs(max_drawdown_pct) if max_drawdown_pct < 0 else Decimal("0")

    recovery = 0
    best_nav = _safe_decimal(equity_rows[0].get("nav"))
    drawdown_length = 0
    worst_recovery = 0
    for row in equity_rows:
        nav = _safe_decimal(row.get("nav"))
        if nav >= best_nav:
            best_nav = nav
            drawdown_length = 0
        else:
            drawdown_length += 1
            worst_recovery = max(worst_recovery, drawdown_length)
    recovery = worst_recovery

    return {
        "annualized_return": decimal_to_str(annualized_return),
        "annualized_volatility": decimal_to_str(annualized_vol),
        "sharpe": decimal_to_str(sharpe),
        "sortino": decimal_to_str(sortino),
        "calmar": decimal_to_str(calmar),
        "recovery_time_bars": str(recovery),
    }


def build_experiment_gate(
    *,
    return_pct: Decimal,
    sharpe: Decimal,
    max_drawdown_pct: Decimal,
    profit_factor: Decimal,
    min_return_pct: Decimal = Decimal("0"),
    min_sharpe: Decimal = Decimal("0.8"),
    max_drawdown_floor_pct: Decimal = Decimal("-0.12"),
    min_profit_factor: Decimal = Decimal("1.1"),
) -> dict[str, Any]:
    checks = [
        {
            "name": "return_pct",
            "value": decimal_to_str(return_pct),
            "threshold": decimal_to_str(min_return_pct),
            "operator": ">=",
            "passed": return_pct >= min_return_pct,
        },
        {
            "name": "sharpe",
            "value": decimal_to_str(sharpe),
            "threshold": decimal_to_str(min_sharpe),
            "operator": ">=",
            "passed": sharpe >= min_sharpe,
        },
        {
            "name": "max_drawdown_pct",
            "value": decimal_to_str(max_drawdown_pct),
            "threshold": decimal_to_str(max_drawdown_floor_pct),
            "operator": ">=",
            "passed": max_drawdown_pct >= max_drawdown_floor_pct,
        },
        {
            "name": "profit_factor",
            "value": decimal_to_str(profit_factor),
            "threshold": decimal_to_str(min_profit_factor),
            "operator": ">=",
            "passed": profit_factor >= min_profit_factor,
        },
    ]
    passed_count = sum(1 for row in checks if row["passed"])
    if passed_count == len(checks):
        status = "pass"
    elif passed_count >= len(checks) - 1:
        status = "watch"
    else:
        status = "fail"
    return {
        "status": status,
        "passed_count": passed_count,
        "total_checks": len(checks),
        "checks": checks,
    }


def record_experiment_run(state_dir: Path | str, entry: dict[str, Any]) -> dict[str, Any]:
    service = LedgerService(state_dir)
    append_jsonl(service.paths.experiment_runs, entry)
    return entry


def load_latest_experiment_run(state_dir: Path | str) -> dict[str, Any] | None:
    payload = read_last_jsonl(LedgerService(state_dir).paths.experiment_runs)
    return payload if isinstance(payload, dict) else None


def load_experiment_runs(state_dir: Path | str, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = read_jsonl(LedgerService(state_dir).paths.experiment_runs)
    items = [row for row in rows if isinstance(row, dict)]
    if limit <= 0:
        return []
    return list(reversed(items[-limit:]))
