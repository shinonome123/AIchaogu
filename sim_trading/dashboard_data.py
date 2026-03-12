from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from sim_trading.ds_operator import (
    deepseek_mode,
    load_latest_ds_approval,
    load_latest_ds_decision,
    load_latest_ds_rejection,
    summarize_ds_approval,
)
from sim_trading.experiments import load_experiment_runs, load_latest_experiment_run
from sim_trading.execution import build_risk_status, load_latest_execution_run, load_latest_risk_event
from sim_trading.ledger import LedgerService
from sim_trading.market import load_latest_market_fetch, load_latest_signal_run
from sim_trading.models import decimal_to_str, now_iso, to_decimal
from sim_trading.notifier import load_report_entries
from sim_trading.storage import read_csv_rows, read_jsonl
from sim_trading.strategy_tracks import STRATEGY_PROFILES, build_strategy_comparison, resolve_strategy_profile, strategy_state_dir
from sim_trading.strategy_tracks import load_strategy_selection
from sim_trading.universe import build_universe_status
from sim_trading.validation import load_latest_validation_run

STRATEGY_TAB_ORDER = ("overview", "baseline", "ds_conservative", "ds_aggressive")


def _equity_curve_timeseries(service: LedgerService) -> list[dict[str, str]]:
    rows = service.normalized_equity_rows()
    return [
        {
            "timestamp": row["timestamp"],
            "cash_balance": row["cash_balance"],
            "positions_market_value": row["positions_market_value"],
            "nav": row["nav"],
            "drawdown_pct": row["drawdown_pct"],
            "realized_pnl_total": row["realized_pnl_total"],
            "unrealized_pnl_total": row["unrealized_pnl_total"],
        }
        for row in rows
    ]


def _market_price_timeseries(service: LedgerService, *, symbols: list[str]) -> dict[str, list[dict[str, str]]]:
    history = {symbol: [] for symbol in symbols}
    if not history:
        return history
    for row in read_jsonl(service.paths.market_feed):
        if not isinstance(row, dict):
            continue
        prices = row.get("prices", {})
        if not isinstance(prices, dict):
            continue
        fallback_timestamp = str(row.get("timestamp", ""))
        for symbol in symbols:
            payload = prices.get(symbol)
            if not isinstance(payload, dict) or "price" not in payload:
                continue
            history[symbol].append(
                {
                    "timestamp": str(payload.get("timestamp", fallback_timestamp)),
                    "price": str(payload["price"]),
                    "source": str(payload.get("source", row.get("source", ""))),
                }
            )
    return history


def _position_mode_summary(mode: str) -> str:
    if mode == "normalized_seed_notional":
        return "normalized seed-notional mode"
    if mode == "synthetic_seed_units":
        return "legacy synthetic seed-unit mode"
    return "standard position mode"


def _position_rows(service: LedgerService, *, snapshot: Any) -> list[dict[str, Any]]:
    positions = service.load_positions()
    rows: list[dict[str, Any]] = []
    for symbol in sorted(positions):
        position = positions[symbol]
        mark = snapshot.marks.get(symbol, position.last_price)
        rows.append(
            {
                "symbol": symbol,
                "quantity": decimal_to_str(position.quantity),
                "average_entry_price": decimal_to_str(position.average_entry_price),
                "last_price": decimal_to_str(position.last_price),
                "mark": decimal_to_str(mark),
                "market_value": decimal_to_str(position.market_value(mark)),
                "unrealized_pnl": decimal_to_str(position.unrealized_pnl(mark)),
                "stop_loss": decimal_to_str(position.stop_loss) if position.stop_loss is not None else "",
                "updated_at": position.updated_at,
            }
        )
    return rows


def _build_context_snapshot(
    state_dir: Path | str,
    *,
    timestamp: str | None = None,
    include_position_mode: bool = False,
    include_universe: bool = False,
    include_strategy_compare: bool = False,
) -> dict[str, Any]:
    service = LedgerService(state_dir)
    account = service.load_account()
    snapshot = service.build_snapshot(timestamp=timestamp or now_iso(), price_overrides=None)
    position_rows = _position_rows(service, snapshot=snapshot)
    equity_rows = service.normalized_equity_rows()
    last_equity_timestamp = equity_rows[-1]["timestamp"] if equity_rows else None

    latest_market_fetch = load_latest_market_fetch(state_dir)
    latest_signal_run = load_latest_signal_run(state_dir)
    latest_execution_run = load_latest_execution_run(state_dir)
    latest_validation_run = load_latest_validation_run(state_dir)
    latest_risk_event = load_latest_risk_event(state_dir)
    latest_ds_decision = load_latest_ds_decision(state_dir)
    latest_ds_rejection = load_latest_ds_rejection(state_dir)
    latest_ds_approval = load_latest_ds_approval(state_dir)
    latest_experiment_run = load_latest_experiment_run(state_dir)
    strategy_selection = load_strategy_selection(state_dir)
    risk_status = build_risk_status(
        state_dir,
        snapshot={"timestamp": snapshot.timestamp, "nav": decimal_to_str(snapshot.nav)},
    )
    held_symbols = [row["symbol"] for row in position_rows]

    payload: dict[str, Any] = {
        "timestamp": snapshot.timestamp,
        "account_id": account.account_id,
        "base_currency": account.base_currency,
        "cash_balance": decimal_to_str(snapshot.cash_balance),
        "positions_market_value": decimal_to_str(snapshot.positions_market_value),
        "nav": decimal_to_str(snapshot.nav),
        "realized_pnl_total": decimal_to_str(snapshot.realized_pnl_total),
        "unrealized_pnl_total": decimal_to_str(snapshot.unrealized_pnl_total),
        "drawdown_pct": decimal_to_str(snapshot.drawdown_pct),
        "drawdown_display": f"{snapshot.drawdown_pct:.2%}",
        "breached_stop_losses": snapshot.breached_stop_losses,
        "position_count": len(position_rows),
        "positions": position_rows,
        "last_equity_snapshot_at": last_equity_timestamp,
        "latest_market_fetch": latest_market_fetch,
        "latest_market_fetch_at": latest_market_fetch.get("timestamp") if latest_market_fetch else None,
        "latest_signal_run": latest_signal_run,
        "latest_signal_run_at": latest_signal_run.get("timestamp") if latest_signal_run else None,
        "latest_signal_summary": latest_signal_run.get("summary") if latest_signal_run else None,
        "latest_execution_run": latest_execution_run,
        "latest_execution_run_at": latest_execution_run.get("timestamp") if latest_execution_run else None,
        "latest_execution_summary": latest_execution_run.get("summary") if latest_execution_run else None,
        "latest_validation_run": latest_validation_run,
        "latest_validation_run_at": latest_validation_run.get("timestamp") if latest_validation_run else None,
        "latest_validation_summary": latest_validation_run.get("summary") if latest_validation_run else None,
        "ds_mode": deepseek_mode(state_dir),
        "latest_ds_decision": latest_ds_decision,
        "latest_ds_decision_at": latest_ds_decision.get("timestamp") if latest_ds_decision else None,
        "latest_ds_decision_summary": latest_ds_decision.get("summary") if latest_ds_decision else None,
        "latest_ds_rejection": latest_ds_rejection,
        "latest_ds_rejection_at": latest_ds_rejection.get("timestamp") if latest_ds_rejection else None,
        "latest_ds_rejection_summary": latest_ds_rejection.get("summary") if latest_ds_rejection else None,
        "latest_ds_approval": latest_ds_approval,
        "latest_ds_approval_at": latest_ds_approval.get("timestamp") if latest_ds_approval else None,
        "latest_ds_approval_summary": summarize_ds_approval(latest_ds_approval),
        "risk_status": risk_status,
        "last_risk_event": latest_risk_event,
        "last_circuit_breaker_event": risk_status.get("last_circuit_breaker_event"),
        "latest_experiment_run": latest_experiment_run,
        "strategy_selection": strategy_selection,
        "timeseries": {
            "equity_curve": _equity_curve_timeseries(service),
            "market_prices": _market_price_timeseries(service, symbols=held_symbols),
        },
    }

    if include_position_mode:
        position_mode = service.position_mode_status()
        payload.update(
            {
                "position_mode": position_mode["mode"],
                "position_mode_summary": _position_mode_summary(position_mode["mode"]),
                "position_mode_is_normalized": position_mode["is_normalized"],
                "position_mode_source_note": position_mode["source_note"],
                "position_normalized_at": position_mode["normalized_at"],
                "position_requires_normalization": position_mode["requires_normalization"],
                "pending_normalization_symbols": position_mode["pending_symbols"],
            }
        )
    if include_universe:
        universe_status = build_universe_status(state_dir)
        payload["universe_status"] = universe_status
        payload["latest_universe_refresh_at"] = universe_status.get("latest_refresh_at")
    if include_strategy_compare:
        payload["strategy_compare"] = build_strategy_comparison(state_dir, timestamp=snapshot.timestamp)

    return payload


def build_status_snapshot(*, state_dir: Path | str, timestamp: str | None = None) -> dict[str, Any]:
    return _build_context_snapshot(
        state_dir,
        timestamp=timestamp,
        include_position_mode=True,
        include_universe=True,
        include_strategy_compare=True,
    )


def _compare_rows(compare_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = compare_payload.get("strategies", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("strategy")): row
        for row in rows
        if isinstance(row, dict) and row.get("strategy")
    }


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return to_decimal(value)
    except Exception:  # noqa: BLE001
        return None


def _strategy_status(row: dict[str, Any] | None) -> str:
    if not row or not row.get("initialized"):
        return "watch"
    max_drawdown = _decimal_or_none(row.get("max_drawdown_pct"))
    breaker = _decimal_or_none(row.get("daily_loss_breaker_pct"))
    if max_drawdown is not None and breaker is not None and max_drawdown <= breaker:
        return "alert"
    if int(row.get("risk_trigger_count", 0) or 0) > 0:
        return "watch"
    return "ok"


def build_strategy_tabs(
    state_dir: Path | str,
    *,
    timestamp: str | None = None,
    strategy_compare: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    compare_payload = strategy_compare or build_strategy_comparison(state_dir, timestamp=timestamp)
    rows_by_strategy = _compare_rows(compare_payload)
    strategy_tabs: list[dict[str, Any]] = []
    strategy_rows = [rows_by_strategy.get(name) for name in STRATEGY_PROFILES]
    initialized_rows = [row for row in strategy_rows if isinstance(row, dict) and row.get("initialized")]
    best_row = None
    if initialized_rows:
        best_row = max(
            initialized_rows,
            key=lambda row: _decimal_or_none(row.get("return_pct")) or Decimal("-999"),
        )
    overview_status = "ok"
    if any(_strategy_status(row) == "alert" for row in strategy_rows):
        overview_status = "alert"
    elif any(_strategy_status(row) == "watch" for row in strategy_rows):
        overview_status = "watch"

    strategy_tabs.append(
        {
            "id": "overview",
            "label": "Overview",
            "view_type": "overview",
            "status": overview_status,
            "strategy_count": len(STRATEGY_PROFILES),
            "initialized_count": len(initialized_rows),
            "best_strategy": best_row.get("strategy") if isinstance(best_row, dict) else None,
            "best_return_pct": best_row.get("return_pct") if isinstance(best_row, dict) else None,
            "generated_at": compare_payload.get("generated_at"),
        }
    )

    for strategy_name in STRATEGY_PROFILES:
        profile = resolve_strategy_profile(strategy_name)
        row = rows_by_strategy.get(strategy_name, {})
        strategy_tabs.append(
            {
                "id": profile.name,
                "label": profile.name,
                "view_type": "strategy",
                "status": _strategy_status(row),
                "initialized": bool(row.get("initialized")),
                "uses_ds": profile.uses_ds,
                "ds_bias": profile.ds_bias,
                "description": profile.description,
                "nav": row.get("nav"),
                "return_pct": row.get("return_pct"),
                "max_drawdown_pct": row.get("max_drawdown_pct"),
                "risk_trigger_count": int(row.get("risk_trigger_count", 0) or 0),
                "position_count": int(row.get("position_count", 0) or 0),
                "daily_loss_breaker_pct": row.get("daily_loss_breaker_pct"),
                "generated_at": compare_payload.get("generated_at"),
            }
        )
    return strategy_tabs


def _latest_timestamp(*values: Any) -> str | None:
    timestamps = [str(value) for value in values if value]
    if not timestamps:
        return None
    return max(timestamps)


def _recent_trades(service: LedgerService, *, limit: int) -> list[dict[str, Any]]:
    rows = read_csv_rows(service.paths.trades)
    return list(reversed(rows[-limit:]))


def _event_entry(
    *,
    timestamp: str | None,
    category: str,
    status: str,
    title: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "category": category,
        "status": status,
        "title": title,
        "detail": detail,
    }


def _recent_events(
    state_dir: Path | str,
    *,
    latest_execution_run: dict[str, Any] | None,
    latest_ds_approval: dict[str, Any] | None,
    latest_ds_rejection: dict[str, Any] | None,
    limit: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    risk_rows = [row for row in read_jsonl(LedgerService(state_dir).paths.risk_events) if isinstance(row, dict)]
    for row in risk_rows[-limit:]:
        events.append(
            _event_entry(
                timestamp=str(row.get("timestamp", "")) or None,
                category="risk",
                status=str(row.get("status", "watch") or "watch"),
                title=str(row.get("type", "risk_event") or "risk_event"),
                detail=str(row.get("reason", "") or row.get("summary", "") or row.get("details", "")),
            )
        )

    if latest_execution_run:
        events.append(
            _event_entry(
                timestamp=str(latest_execution_run.get("timestamp", "")) or None,
                category="execution",
                status=str(latest_execution_run.get("status", "ok") or "ok"),
                title=str(latest_execution_run.get("summary", "execution") or "execution"),
                detail=(
                    f"fills={latest_execution_run.get('fills_count', 0)} "
                    + f"rejected={latest_execution_run.get('rejected_orders', 0)} "
                    + f"canceled={latest_execution_run.get('canceled_orders', 0)}"
                ),
            )
        )
    if latest_ds_approval:
        events.append(
            _event_entry(
                timestamp=str(latest_ds_approval.get("timestamp", "")) or None,
                category="ds",
                status=str(latest_ds_approval.get("status", "approved") or "approved"),
                title="ds_approval",
                detail=str(latest_ds_approval.get("decision_summary", "") or summarize_ds_approval(latest_ds_approval) or ""),
            )
        )
    if latest_ds_rejection:
        events.append(
            _event_entry(
                timestamp=str(latest_ds_rejection.get("timestamp", "")) or None,
                category="ds",
                status=str(latest_ds_rejection.get("status", "rejected") or "rejected"),
                title="ds_rejection",
                detail=str(latest_ds_rejection.get("reason", "") or latest_ds_rejection.get("summary", "") or ""),
            )
        )

    events.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return events[:limit]


def _positions_summary(context: dict[str, Any]) -> dict[str, Any]:
    nav = _decimal_or_none(context.get("nav")) or Decimal("0")
    positions_market_value = _decimal_or_none(context.get("positions_market_value")) or Decimal("0")
    cash_balance = _decimal_or_none(context.get("cash_balance")) or Decimal("0")
    positions = context.get("positions", [])
    largest_position = None
    if isinstance(positions, list) and positions:
        largest_position = max(
            (row for row in positions if isinstance(row, dict)),
            key=lambda row: _decimal_or_none(row.get("market_value")) or Decimal("0"),
        )
    gross_exposure_pct = Decimal("0")
    cash_ratio_pct = Decimal("0")
    if nav > 0:
        gross_exposure_pct = positions_market_value / nav
        cash_ratio_pct = cash_balance / nav
    return {
        "gross_exposure_pct": decimal_to_str(gross_exposure_pct),
        "cash_ratio_pct": decimal_to_str(cash_ratio_pct),
        "largest_position_symbol": largest_position.get("symbol") if isinstance(largest_position, dict) else None,
        "largest_position_value": largest_position.get("market_value") if isinstance(largest_position, dict) else None,
        "breached_stop_losses": context.get("breached_stop_losses", []),
    }


def _empty_strategy_detail(state_dir: Path | str, strategy: str) -> dict[str, Any]:
    profile = resolve_strategy_profile(strategy)
    return {
        "strategy": profile.name,
        "label": profile.name,
        "initialized": False,
        "state_dir": str(strategy_state_dir(state_dir, profile.name)),
        "timestamp": now_iso(),
        "profile": {
            "name": profile.name,
            "uses_ds": profile.uses_ds,
            "ds_bias": profile.ds_bias,
            "universe_artifact": profile.universe_artifact,
            "daily_loss_breaker_pct": decimal_to_str(-profile.daily_loss_cap_pct),
            "description": profile.description,
        },
        "summary": {
            "nav": None,
            "return_pct": None,
            "current_drawdown_pct": None,
            "max_drawdown_pct": None,
            "risk_trigger_count": 0,
            "position_count": 0,
            "turnover_ratio": None,
            "win_rate": None,
            "profit_factor": None,
            "latest_updated_at": None,
        },
        "positions_summary": {
            "gross_exposure_pct": "0",
            "cash_ratio_pct": "0",
            "largest_position_symbol": None,
            "largest_position_value": None,
            "breached_stop_losses": [],
        },
        "positions": [],
        "recent_trades": [],
        "recent_events": [],
        "timeseries": {"equity_curve": [], "market_prices": {}},
        "risk_status": {
            "timestamp": now_iso(),
            "blocked_new_orders": False,
            "blocked_reasons": [],
            "kill_switch_enabled": False,
            "kill_switch_reason": "",
            "consecutive_loss_count": 0,
            "consecutive_loss_limit": 0,
            "cooldown_remaining_cycles": 0,
            "daily_loss_circuit_breaker_pct": decimal_to_str(-profile.daily_loss_cap_pct),
            "daily_return_pct": "0",
            "day_open_nav": "0",
            "max_position_weight_pct": "0",
            "max_gross_exposure_pct": "0",
            "max_concurrent_positions": 0,
            "circuit_breaker_tripped": False,
            "last_circuit_breaker_event": None,
            "last_risk_event": None,
            "updated_at": now_iso(),
        },
        "ds_mode": "disabled",
        "latest_ds_decision": None,
        "latest_ds_decision_summary": None,
        "latest_ds_rejection": None,
        "latest_ds_rejection_summary": None,
        "latest_ds_approval": None,
        "latest_ds_approval_summary": None,
        "latest_market_fetch": None,
        "latest_signal_run": None,
        "latest_execution_run": None,
        "latest_validation_run": None,
        "last_circuit_breaker_event": None,
    }


def build_strategy_detail(
    state_dir: Path | str,
    *,
    strategy: str,
    timestamp: str | None = None,
    trade_limit: int = 8,
    event_limit: int = 8,
) -> dict[str, Any]:
    profile = resolve_strategy_profile(strategy)
    strategy_dir = strategy_state_dir(state_dir, profile.name)
    if not (strategy_dir / "account.json").exists():
        return _empty_strategy_detail(state_dir, profile.name)

    context = _build_context_snapshot(strategy_dir, timestamp=timestamp)
    compare_payload = build_strategy_comparison(state_dir, timestamp=context["timestamp"])
    compare_row = _compare_rows(compare_payload).get(profile.name, {})
    service = LedgerService(strategy_dir)

    context.update(
        {
            "strategy": profile.name,
            "label": profile.name,
            "initialized": True,
            "state_dir": str(strategy_dir),
            "profile": {
                "name": profile.name,
                "uses_ds": profile.uses_ds,
                "ds_bias": profile.ds_bias,
                "universe_artifact": profile.universe_artifact,
                "daily_loss_breaker_pct": decimal_to_str(-profile.daily_loss_cap_pct),
                "description": profile.description,
            },
            "summary": {
                "nav": context["nav"],
                "return_pct": compare_row.get("return_pct"),
                "current_drawdown_pct": context["drawdown_pct"],
                "max_drawdown_pct": compare_row.get("max_drawdown_pct"),
                "risk_trigger_count": int(compare_row.get("risk_trigger_count", 0) or 0),
                "position_count": int(context.get("position_count", 0) or 0),
                "turnover_ratio": compare_row.get("turnover_ratio"),
                "win_rate": compare_row.get("win_rate"),
                "profit_factor": compare_row.get("profit_factor"),
                "latest_updated_at": _latest_timestamp(
                    context.get("latest_execution_run_at"),
                    context.get("latest_signal_run_at"),
                    context.get("latest_validation_run_at"),
                    context.get("last_equity_snapshot_at"),
                ),
            },
            "positions_summary": _positions_summary(context),
            "recent_trades": _recent_trades(service, limit=trade_limit),
            "recent_events": _recent_events(
                strategy_dir,
                latest_execution_run=context.get("latest_execution_run"),
                latest_ds_approval=context.get("latest_ds_approval"),
                latest_ds_rejection=context.get("latest_ds_rejection"),
                limit=event_limit,
            ),
        }
    )
    return context


def build_dashboard_status_payload(
    *,
    state_dir: Path | str,
    report_log: Path | str,
    notification_limit: int,
    timestamp: str | None = None,
) -> dict[str, Any]:
    snapshot = build_status_snapshot(state_dir=state_dir, timestamp=timestamp)
    strategy_tabs = build_strategy_tabs(
        state_dir,
        timestamp=snapshot.get("timestamp"),
        strategy_compare=snapshot.get("strategy_compare"),
    )
    return {
        "ok": True,
        "snapshot": snapshot,
        "strategy_tabs": strategy_tabs,
        "default_strategy_view": "overview",
        "latest_market_fetch": snapshot.get("latest_market_fetch"),
        "latest_signal_run": snapshot.get("latest_signal_run"),
        "latest_execution_run": snapshot.get("latest_execution_run"),
        "latest_validation_run": snapshot.get("latest_validation_run"),
        "latest_experiment_run": snapshot.get("latest_experiment_run"),
        "experiment_history": load_experiment_runs(state_dir, limit=12),
        "latest_ds_decision": snapshot.get("latest_ds_decision"),
        "latest_ds_decision_summary": snapshot.get("latest_ds_decision_summary"),
        "latest_ds_rejection": snapshot.get("latest_ds_rejection"),
        "latest_ds_rejection_summary": snapshot.get("latest_ds_rejection_summary"),
        "latest_ds_approval": snapshot.get("latest_ds_approval"),
        "latest_ds_approval_summary": snapshot.get("latest_ds_approval_summary"),
        "ds_mode": snapshot.get("ds_mode"),
        "universe_status": snapshot.get("universe_status"),
        "strategy_compare": snapshot.get("strategy_compare"),
        "risk_status": snapshot.get("risk_status"),
        "latest_notifications": load_report_entries(report_log, limit=notification_limit),
        "report_log": str(report_log),
    }
