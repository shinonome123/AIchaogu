from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from sim_trading.ledger import LedgerService
from sim_trading.market import load_latest_signal_run, run_signal_snapshot
from sim_trading.models import (
    Position,
    decimal_to_str,
    normalize_symbol,
    now_iso,
    quantize_8,
    to_decimal,
)
from sim_trading.risk import RiskManager, RiskViolation
from sim_trading.storage import append_jsonl, read_jsonl, read_last_jsonl

OPEN_ORDER_STATUSES = {"pending", "partial"}


@dataclass(frozen=True)
class ExecutionCycleResult:
    entry: dict[str, Any]


def load_latest_execution_run(state_dir: Path | str) -> dict[str, Any] | None:
    payload = read_last_jsonl(LedgerService(state_dir).paths.execution_runs)
    return payload if isinstance(payload, dict) else None


def load_latest_risk_event(state_dir: Path | str) -> dict[str, Any] | None:
    payload = read_last_jsonl(LedgerService(state_dir).paths.risk_events)
    return payload if isinstance(payload, dict) else None


def _price_map_from_entry(entry: dict[str, Any]) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    raw_prices = entry.get("prices", {})
    if not isinstance(raw_prices, dict):
        return prices
    for symbol, payload in raw_prices.items():
        if not isinstance(payload, dict) or "price" not in payload:
            continue
        prices[normalize_symbol(symbol)] = quantize_8(to_decimal(payload["price"]))
    return prices


def _resolve_price_map(
    service: LedgerService,
    *,
    symbols: set[str],
    price_overrides: dict[str, Decimal] | None = None,
) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    latest_feed = read_last_jsonl(service.paths.market_feed)
    if isinstance(latest_feed, dict):
        prices.update(_price_map_from_entry(latest_feed))

    stored_prices = service.load_market_prices()
    for symbol, payload in stored_prices.items():
        if symbol not in symbols and normalize_symbol(symbol) not in symbols:
            continue
        if isinstance(payload, dict) and "price" in payload:
            prices[normalize_symbol(symbol)] = quantize_8(to_decimal(payload["price"]))

    for symbol, price in (price_overrides or {}).items():
        prices[normalize_symbol(symbol)] = quantize_8(price)

    return {symbol: prices[symbol] for symbol in symbols if symbol in prices}


def _day_return_pct(service: LedgerService, *, snapshot_timestamp: str, nav: Decimal) -> tuple[Decimal, Decimal]:
    target_day = datetime.fromisoformat(snapshot_timestamp).date()
    day_open_nav = service.day_open_nav(target_day) or nav
    if day_open_nav <= 0:
        return Decimal("0"), day_open_nav
    return quantize_8((nav / day_open_nav) - Decimal("1")), day_open_nav


def build_risk_status(
    state_dir: Path | str,
    *,
    snapshot: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    service = LedgerService(state_dir)
    risk_config = service.load_risk_config()
    risk_state = service.load_risk_state()
    if snapshot is None:
        current_snapshot = service.build_snapshot(timestamp=timestamp or now_iso())
        snapshot_payload = {
            "timestamp": current_snapshot.timestamp,
            "nav": decimal_to_str(current_snapshot.nav),
        }
        nav = current_snapshot.nav
    else:
        snapshot_payload = snapshot
        nav = to_decimal(snapshot["nav"])
    snapshot_timestamp = str(snapshot_payload.get("timestamp", timestamp or now_iso()))
    day_return_pct, day_open_nav = _day_return_pct(service, snapshot_timestamp=snapshot_timestamp, nav=nav)

    reasons: list[str] = []
    if bool(risk_state.get("kill_switch_enabled")):
        reason = str(risk_state.get("kill_switch_reason", "")).strip() or "kill switch enabled"
        reasons.append(reason)
    if int(risk_state.get("cooldown_remaining_cycles", 0)) > 0:
        reasons.append(
            "cooldown active"
            + f" ({int(risk_state.get('cooldown_remaining_cycles', 0))} cycle(s) remaining)"
        )
    if day_return_pct <= risk_config.daily_loss_circuit_breaker_pct:
        reasons.append(
            "daily loss circuit breaker hit"
            + f" ({day_return_pct:.2%} <= {risk_config.daily_loss_circuit_breaker_pct:.2%})"
        )

    last_risk_event = load_latest_risk_event(state_dir)
    return {
        "timestamp": snapshot_timestamp,
        "blocked_new_orders": bool(reasons),
        "blocked_reasons": reasons,
        "kill_switch_enabled": bool(risk_state.get("kill_switch_enabled")),
        "kill_switch_reason": str(risk_state.get("kill_switch_reason", "")).strip(),
        "consecutive_loss_count": int(risk_state.get("consecutive_loss_count", 0)),
        "consecutive_loss_limit": risk_config.consecutive_loss_limit,
        "cooldown_remaining_cycles": int(risk_state.get("cooldown_remaining_cycles", 0)),
        "daily_loss_circuit_breaker_pct": decimal_to_str(risk_config.daily_loss_circuit_breaker_pct),
        "daily_return_pct": decimal_to_str(day_return_pct),
        "day_open_nav": decimal_to_str(day_open_nav),
        "max_position_weight_pct": decimal_to_str(risk_config.max_position_weight_pct),
        "max_gross_exposure_pct": decimal_to_str(risk_config.max_gross_exposure_pct),
        "max_concurrent_positions": risk_config.max_concurrent_positions,
        "circuit_breaker_tripped": day_return_pct <= risk_config.daily_loss_circuit_breaker_pct,
        "last_circuit_breaker_event": risk_state.get("last_circuit_breaker_event"),
        "last_risk_event": last_risk_event,
        "updated_at": str(risk_state.get("updated_at", snapshot_timestamp)),
    }


def set_kill_switch(
    state_dir: Path | str,
    *,
    enabled: bool,
    reason: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    service = LedgerService(state_dir)
    change_time = timestamp or now_iso()
    risk_state = service.load_risk_state()
    risk_state["kill_switch_enabled"] = enabled
    risk_state["kill_switch_reason"] = reason.strip()
    risk_state["updated_at"] = change_time
    service.save_risk_state(risk_state)
    event = {
        "timestamp": change_time,
        "type": "kill_switch_toggled",
        "status": "blocked" if enabled else "info",
        "reason": reason.strip() or ("kill switch enabled" if enabled else "kill switch disabled"),
        "details": {
            "kill_switch_enabled": enabled,
        },
    }
    append_jsonl(service.paths.risk_events, event)
    return event


def _current_order_book(service: LedgerService) -> dict[str, dict[str, Any]]:
    book: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(service.paths.order_events):
        if not isinstance(row, dict):
            continue
        order_id = str(row.get("order_id", "")).strip()
        if not order_id:
            continue
        book[order_id] = row
    return book


def _append_order_event(service: LedgerService, payload: dict[str, Any]) -> None:
    append_jsonl(service.paths.order_events, payload)


def _append_risk_event(service: LedgerService, payload: dict[str, Any]) -> None:
    append_jsonl(service.paths.risk_events, payload)


def _target_quantity(nav: Decimal, target_weight: Decimal, price: Decimal) -> Decimal:
    if nav <= 0 or price <= 0 or target_weight <= 0:
        return Decimal("0")
    return quantize_8((nav * target_weight) / price)


def _remaining_required_quantity(
    *,
    side: str,
    current_position: Position | None,
    target_quantity: Decimal,
) -> Decimal:
    current_quantity = current_position.quantity if current_position else Decimal("0")
    if side == "buy":
        return max(Decimal("0"), quantize_8(target_quantity - current_quantity))
    return max(Decimal("0"), quantize_8(current_quantity - target_quantity))


def _estimate_fill_values(
    *,
    quantity: Decimal,
    mark_price: Decimal,
    side: str,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    slippage_ratio = slippage_bps / Decimal("10000")
    fee_ratio = fee_bps / Decimal("10000")
    if side == "buy":
        fill_price = quantize_8(mark_price * (Decimal("1") + slippage_ratio))
    else:
        fill_price = quantize_8(mark_price * (Decimal("1") - slippage_ratio))
    fill_notional = quantize_8(fill_price * quantity)
    fee = quantize_8(fill_notional * fee_ratio)
    slippage_value = quantize_8(abs(fill_price - mark_price) * quantity)
    return fill_price, fee, slippage_value


def _planned_fill_quantity(
    *,
    requested_quantity: Decimal,
    remaining_quantity: Decimal,
    needed_quantity: Decimal,
    mark_price: Decimal,
    nav: Decimal,
    pending_cycles: int,
    partial_fill_ratio: Decimal,
    partial_fill_threshold_pct: Decimal,
) -> Decimal:
    if remaining_quantity <= 0 or needed_quantity <= 0:
        return Decimal("0")
    remaining = min(remaining_quantity, needed_quantity)
    if pending_cycles >= 1:
        return quantize_8(remaining)

    requested_notional = quantize_8(requested_quantity * mark_price)
    if nav > 0 and requested_notional / nav >= partial_fill_threshold_pct:
        return quantize_8(max(remaining * partial_fill_ratio, Decimal("0")))
    return quantize_8(remaining)


def _record_circuit_breaker_if_needed(
    service: LedgerService,
    *,
    execution_id: str,
    snapshot_timestamp: str,
    snapshot_nav: Decimal,
) -> None:
    risk_status = build_risk_status(
        service.paths.root,
        snapshot={"timestamp": snapshot_timestamp, "nav": decimal_to_str(snapshot_nav)},
    )
    if not risk_status["circuit_breaker_tripped"]:
        return
    risk_state = service.load_risk_state()
    last_event = risk_state.get("last_circuit_breaker_event")
    trading_day = snapshot_timestamp.split("T", 1)[0]
    if isinstance(last_event, dict) and last_event.get("trading_day") == trading_day:
        return
    event = {
        "timestamp": snapshot_timestamp,
        "execution_id": execution_id,
        "type": "daily_loss_circuit_breaker",
        "status": "blocked",
        "reason": (
            "daily loss circuit breaker hit"
            + f" ({risk_status['daily_return_pct']} <= {risk_status['daily_loss_circuit_breaker_pct']})"
        ),
        "details": {
            "daily_return_pct": risk_status["daily_return_pct"],
            "threshold_pct": risk_status["daily_loss_circuit_breaker_pct"],
            "day_open_nav": risk_status["day_open_nav"],
            "nav": decimal_to_str(snapshot_nav),
            "trading_day": trading_day,
        },
    }
    _append_risk_event(service, event)
    risk_state["last_circuit_breaker_event"] = {
        "timestamp": snapshot_timestamp,
        "trading_day": trading_day,
        "daily_return_pct": risk_status["daily_return_pct"],
        "threshold_pct": risk_status["daily_loss_circuit_breaker_pct"],
    }
    risk_state["updated_at"] = snapshot_timestamp
    service.save_risk_state(risk_state)


class SimulationExecutor:
    def __init__(self, state_dir: Path | str) -> None:
        self.service = LedgerService(state_dir)

    def execute_cycle(
        self,
        *,
        timestamp: str | None = None,
        signal_run_entry: dict[str, Any] | None = None,
        source: str = "cli.execute-sim",
        lookback_points: int = 6,
        price_overrides: dict[str, Decimal] | None = None,
    ) -> ExecutionCycleResult:
        run_time = timestamp or now_iso()
        execution_id = f"EXEC-{uuid4().hex[:12].upper()}"
        service = self.service
        execution_config = service.load_execution_config()
        risk_config = service.load_risk_config()
        risk_manager = RiskManager(risk_config)

        signal_entry = signal_run_entry
        if signal_entry is None:
            signal_entry = load_latest_signal_run(service.paths.root)
            if signal_entry is None and execution_config.auto_run_signals:
                signal_entry = run_signal_snapshot(
                    state_dir=service.paths.root,
                    source=f"{source}.signals",
                    lookback_points=lookback_points,
                    timestamp=run_time,
                ).entry
        if signal_entry is None:
            raise FileNotFoundError("no signal snapshot available; run run-signals or pass signal_run_entry")

        targets = signal_entry.get("targets", [])
        target_weights: dict[str, Decimal] = {}
        target_rationales: dict[str, str] = {}
        target_stop_loss_pcts: dict[str, Decimal] = {}
        target_take_profit_pcts: dict[str, Decimal] = {}
        target_actions: dict[str, str] = {}
        target_confidences: dict[str, str] = {}
        if isinstance(targets, list):
            for item in targets:
                if not isinstance(item, dict) or "symbol" not in item or "target_weight" not in item:
                    continue
                symbol = normalize_symbol(str(item["symbol"]))
                target_weights[symbol] = to_decimal(item["target_weight"])
                target_rationales[symbol] = str(item.get("rationale", ""))
                target_actions[symbol] = str(item.get("action", "")).strip().lower()
                target_confidences[symbol] = str(item.get("confidence", "")).strip()
                if "stop_loss_pct" in item:
                    target_stop_loss_pcts[symbol] = to_decimal(item.get("stop_loss_pct", "0"))
                if "take_profit_pct" in item:
                    target_take_profit_pcts[symbol] = to_decimal(item.get("take_profit_pct", "0"))

        positions = service.load_positions()
        symbols = set(target_weights) | set(positions)
        price_map = _resolve_price_map(service, symbols=symbols, price_overrides=price_overrides)
        snapshot_before = service.build_snapshot(timestamp=run_time, price_overrides=price_map or None)
        _record_circuit_breaker_if_needed(
            service,
            execution_id=execution_id,
            snapshot_timestamp=run_time,
            snapshot_nav=snapshot_before.nav,
        )
        open_orders_before = [
            row
            for row in _current_order_book(service).values()
            if str(row.get("status", "")) in OPEN_ORDER_STATUSES
        ]

        cycle_order_rows: dict[str, dict[str, Any]] = {}
        fill_rows: list[dict[str, Any]] = []
        rejection_rows: list[dict[str, Any]] = []
        cancel_rows: list[dict[str, Any]] = []
        slippage_total = Decimal("0")
        fees_total = Decimal("0")
        realized_pnl = Decimal("0")

        def update_cycle_order(row: dict[str, Any]) -> None:
            cycle_order_rows[str(row["order_id"])] = row

        def append_cancel(order: dict[str, Any], reason: str) -> None:
            event = {
                **order,
                "timestamp": run_time,
                "execution_id": execution_id,
                "event_type": "cancel",
                "status": "canceled",
                "reason": reason,
                "pending_cycles": int(order.get("pending_cycles", 0)),
            }
            _append_order_event(service, event)
            cancel_rows.append(event)
            update_cycle_order(event)

        def append_rejection(order: dict[str, Any], reason: str, *, risk_event_type: str = "order_rejected") -> None:
            event = {
                **order,
                "timestamp": run_time,
                "execution_id": execution_id,
                "event_type": "reject",
                "status": "rejected",
                "reason": reason,
                "pending_cycles": int(order.get("pending_cycles", 0)),
            }
            _append_order_event(service, event)
            rejection_rows.append(event)
            update_cycle_order(event)
            _append_risk_event(
                service,
                {
                    "timestamp": run_time,
                    "execution_id": execution_id,
                    "order_id": event["order_id"],
                    "symbol": event["symbol"],
                    "type": risk_event_type,
                    "status": "rejected",
                    "reason": reason,
                    "details": {
                        "side": event["side"],
                        "requested_quantity": event["requested_quantity"],
                    },
                },
            )

        def try_fill(
            order: dict[str, Any],
            *,
            current_position: Position | None,
            target_weight: Decimal,
        ) -> None:
            nonlocal slippage_total, fees_total, realized_pnl
            symbol = str(order["symbol"])
            side = str(order["side"])
            mark_price = price_map.get(symbol)
            if mark_price is None or mark_price <= 0:
                append_cancel(order, "missing market price")
                return

            current_snapshot = service.build_snapshot(timestamp=run_time, price_overrides=price_map or None)
            target_quantity = _target_quantity(current_snapshot.nav, target_weight, mark_price)
            needed_quantity = _remaining_required_quantity(
                side=side,
                current_position=current_position,
                target_quantity=target_quantity,
            )
            if needed_quantity <= 0:
                append_cancel(order, "target no longer requires this order")
                return

            pending_cycles = int(order.get("pending_cycles", 0))
            if pending_cycles >= execution_config.cancel_pending_after_cycles:
                append_cancel(order, "pending order expired")
                return

            if side == "buy":
                dynamic_risk = build_risk_status(
                    service.paths.root,
                    snapshot={"timestamp": run_time, "nav": decimal_to_str(current_snapshot.nav)},
                )
                if dynamic_risk["blocked_new_orders"]:
                    append_cancel(order, "; ".join(dynamic_risk["blocked_reasons"]))
                    return

            requested_quantity = to_decimal(order["requested_quantity"])
            remaining_quantity = to_decimal(order["remaining_quantity"])
            fill_quantity = _planned_fill_quantity(
                requested_quantity=requested_quantity,
                remaining_quantity=remaining_quantity,
                needed_quantity=needed_quantity,
                mark_price=mark_price,
                nav=current_snapshot.nav,
                pending_cycles=pending_cycles,
                partial_fill_ratio=execution_config.partial_fill_ratio,
                partial_fill_threshold_pct=execution_config.partial_fill_threshold_pct,
            )
            if fill_quantity <= 0:
                append_cancel(order, "fillable quantity rounded to zero")
                return

            fill_price, fee, slippage_value = _estimate_fill_values(
                quantity=fill_quantity,
                mark_price=mark_price,
                side=side,
                fee_bps=execution_config.fee_bps,
                slippage_bps=execution_config.slippage_bps,
            )
            target_stop_loss_pct = to_decimal(order.get("target_stop_loss_pct", "0"))
            target_take_profit_pct = to_decimal(order.get("target_take_profit_pct", "0"))
            stop_loss_override = None
            if side == "buy" and target_stop_loss_pct > 0:
                stop_loss_override = quantize_8(fill_price * (Decimal("1") - target_stop_loss_pct))
            provided_stop_loss = stop_loss_override
            if provided_stop_loss is None and current_position is not None:
                provided_stop_loss = current_position.stop_loss
            target_take_profit = None
            if side == "buy" and target_take_profit_pct > 0:
                target_take_profit = quantize_8(fill_price * (Decimal("1") + target_take_profit_pct))
            trade = service.record_trade(
                symbol=symbol,
                side=side,
                quantity=fill_quantity,
                price=fill_price,
                fee=fee,
                timestamp=run_time,
                strategy=str(signal_entry.get("source", "signal-run")),
                note=f"sim-execution order={order['order_id']} execution={execution_id}",
                stop_loss=provided_stop_loss,
                enforce_risk_checks=False,
            )

            total_filled = quantize_8(to_decimal(order.get("filled_quantity_total", "0")) + fill_quantity)
            remaining_after = max(Decimal("0"), quantize_8(remaining_quantity - fill_quantity))
            status = "filled" if remaining_after <= 0 else "partial"
            event = {
                **order,
                "timestamp": run_time,
                "execution_id": execution_id,
                "event_type": "fill",
                "status": status,
                "fill_quantity": decimal_to_str(fill_quantity),
                "filled_quantity_total": decimal_to_str(total_filled),
                "remaining_quantity": decimal_to_str(remaining_after),
                "avg_fill_price": decimal_to_str(fill_price),
                "mark_price": decimal_to_str(mark_price),
                "fee": decimal_to_str(fee),
                "slippage": decimal_to_str(slippage_value),
                "pending_cycles": pending_cycles + (1 if status == "partial" else pending_cycles),
                "reason": "" if status == "filled" else "partial fill carried forward",
                "trade_id": trade.trade_id,
                "realized_pnl": decimal_to_str(trade.realized_pnl),
                "target_stop_loss": decimal_to_str(stop_loss_override) if stop_loss_override is not None else "",
                "target_take_profit": decimal_to_str(target_take_profit) if target_take_profit is not None else "",
            }
            _append_order_event(service, event)
            fill_rows.append(event)
            update_cycle_order(event)
            fees_total += fee
            slippage_total += slippage_value
            realized_pnl += trade.realized_pnl

        for order in sorted(open_orders_before, key=lambda row: (str(row.get("symbol", "")), str(row.get("order_id", "")))):
            current_positions = service.load_positions()
            current_position = current_positions.get(str(order.get("symbol", "")))
            target_weight = target_weights.get(str(order.get("symbol", "")), Decimal("0"))
            try_fill(order, current_position=current_position, target_weight=target_weight)

        order_book_after_open = _current_order_book(service)
        open_symbols = {
            str(row.get("symbol", ""))
            for row in order_book_after_open.values()
            if str(row.get("status", "")) in OPEN_ORDER_STATUSES
        }

        order_candidates: list[dict[str, Any]] = []
        for symbol in sorted(symbols):
            if symbol in open_symbols:
                continue
            mark_price = price_map.get(symbol)
            current_positions = service.load_positions()
            current_position = current_positions.get(symbol)
            current_snapshot = service.build_snapshot(timestamp=run_time, price_overrides=price_map or None)
            target_weight = target_weights.get(symbol, Decimal("0"))
            if mark_price is None or mark_price <= 0:
                if target_weight > 0 or current_position is not None:
                    order_id = f"ORD-{uuid4().hex[:12].upper()}"
                    rejected = {
                        "order_id": order_id,
                        "symbol": symbol,
                        "side": "buy" if target_weight > 0 else "sell",
                        "requested_quantity": "0",
                        "filled_quantity_total": "0",
                        "remaining_quantity": "0",
                        "target_weight": decimal_to_str(target_weight),
                        "target_notional": decimal_to_str(current_snapshot.nav * target_weight),
                        "target_rationale": target_rationales.get(symbol, ""),
                        "target_action": target_actions.get(symbol, ""),
                        "target_confidence": target_confidences.get(symbol, ""),
                        "target_stop_loss_pct": decimal_to_str(target_stop_loss_pcts.get(symbol, Decimal("0"))),
                        "target_take_profit_pct": decimal_to_str(target_take_profit_pcts.get(symbol, Decimal("0"))),
                        "created_at": run_time,
                        "pending_cycles": 0,
                    }
                    append_rejection(rejected, "missing market price", risk_event_type="order_rejected_missing_price")
                continue

            target_quantity = _target_quantity(current_snapshot.nav, target_weight, mark_price)
            current_quantity = current_position.quantity if current_position else Decimal("0")
            delta_quantity = quantize_8(target_quantity - current_quantity)
            if delta_quantity == 0:
                continue
            side = "buy" if delta_quantity > 0 else "sell"
            order_quantity = abs(delta_quantity)
            notional = quantize_8(order_quantity * mark_price)
            if side == "buy" and notional < execution_config.min_order_notional:
                continue
            if side == "sell" and order_quantity <= 0:
                continue
            order_candidates.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "order_quantity": order_quantity,
                    "target_weight": target_weight,
                    "target_notional": current_snapshot.nav * target_weight,
                    "current_position": current_position,
                    "mark_price": mark_price,
                }
            )

        for candidate in sorted(order_candidates, key=lambda item: (0 if item["side"] == "sell" else 1, item["symbol"])):
            symbol = str(candidate["symbol"])
            side = str(candidate["side"])
            order_quantity = to_decimal(candidate["order_quantity"])
            target_weight = to_decimal(candidate["target_weight"])
            current_position = candidate["current_position"]
            mark_price = to_decimal(candidate["mark_price"])
            current_snapshot = service.build_snapshot(timestamp=run_time, price_overrides=price_map or None)
            clip_reason = ""

            if side == "buy":
                current_quantity = current_position.quantity if current_position else Decimal("0")
                estimated_fill_price, _, _ = _estimate_fill_values(
                    quantity=order_quantity,
                    mark_price=mark_price,
                    side=side,
                    fee_bps=execution_config.fee_bps,
                    slippage_bps=execution_config.slippage_bps,
                )
                current_notional = quantize_8(current_quantity * estimated_fill_price)
                max_symbol_notional = quantize_8(current_snapshot.nav * risk_config.max_position_weight_pct)
                remaining_symbol_notional = max(Decimal("0"), quantize_8(max_symbol_notional - current_notional))
                per_unit_cost = quantize_8(estimated_fill_price * (Decimal("1") + (execution_config.fee_bps / Decimal("10000"))))
                cash_limited_quantity = (
                    quantize_8(service.load_account().cash_balance / per_unit_cost)
                    if per_unit_cost > 0
                    else Decimal("0")
                )
                other_gross_exposure = Decimal("0")
                active_positions = 0
                for current_symbol, position in service.load_positions().items():
                    if current_symbol == symbol:
                        continue
                    active_positions += 1
                    other_mark = price_map.get(current_symbol, position.last_price)
                    other_gross_exposure += quantize_8(position.quantity * other_mark)
                gross_cap = quantize_8(current_snapshot.nav * risk_config.max_gross_exposure_pct)
                remaining_gross_notional = max(
                    Decimal("0"),
                    quantize_8(gross_cap - other_gross_exposure - current_notional),
                )
                gross_limited_quantity = (
                    quantize_8(remaining_gross_notional / estimated_fill_price)
                    if estimated_fill_price > 0
                    else Decimal("0")
                )
                symbol_limited_quantity = (
                    quantize_8(remaining_symbol_notional / estimated_fill_price)
                    if estimated_fill_price > 0
                    else Decimal("0")
                )
                if current_position is None and active_positions >= risk_config.max_concurrent_positions:
                    gross_limited_quantity = Decimal("0")
                adjusted_quantity = min(
                    order_quantity,
                    cash_limited_quantity,
                    symbol_limited_quantity,
                    gross_limited_quantity,
                )
                if adjusted_quantity <= 0:
                    order_id = f"ORD-{uuid4().hex[:12].upper()}"
                    rejected = {
                        "order_id": order_id,
                        "symbol": symbol,
                        "side": side,
                        "requested_quantity": decimal_to_str(order_quantity),
                        "filled_quantity_total": "0",
                        "remaining_quantity": decimal_to_str(order_quantity),
                        "target_weight": decimal_to_str(target_weight),
                        "target_notional": decimal_to_str(current_snapshot.nav * target_weight),
                        "target_rationale": target_rationales.get(symbol, ""),
                        "target_action": target_actions.get(symbol, ""),
                        "target_confidence": target_confidences.get(symbol, ""),
                        "target_stop_loss_pct": decimal_to_str(target_stop_loss_pcts.get(symbol, Decimal("0"))),
                        "target_take_profit_pct": decimal_to_str(target_take_profit_pcts.get(symbol, Decimal("0"))),
                        "created_at": run_time,
                        "pending_cycles": 0,
                    }
                    rejection_reason = (
                        f"max concurrent positions reached ({risk_config.max_concurrent_positions})"
                        if current_position is None and active_positions >= risk_config.max_concurrent_positions
                        else "no buy capacity after max-position, gross exposure, and cash caps"
                    )
                    append_rejection(rejected, rejection_reason, risk_event_type="order_rejected_risk_gate")
                    continue
                if adjusted_quantity < order_quantity:
                    order_quantity = adjusted_quantity
                    clip_reason = "quantity clipped by max-position, gross exposure, or cash cap"

            order_id = f"ORD-{uuid4().hex[:12].upper()}"
            pending = {
                "timestamp": run_time,
                "created_at": run_time,
                "execution_id": execution_id,
                "order_id": order_id,
                "event_type": "create",
                "status": "pending",
                "symbol": symbol,
                "side": side,
                "requested_quantity": decimal_to_str(order_quantity),
                "filled_quantity_total": "0",
                "remaining_quantity": decimal_to_str(order_quantity),
                "target_weight": decimal_to_str(target_weight),
                "target_notional": decimal_to_str(current_snapshot.nav * target_weight),
                "target_rationale": target_rationales.get(symbol, ""),
                "target_action": target_actions.get(symbol, ""),
                "target_confidence": target_confidences.get(symbol, ""),
                "target_stop_loss_pct": decimal_to_str(target_stop_loss_pcts.get(symbol, Decimal("0"))),
                "target_take_profit_pct": decimal_to_str(target_take_profit_pcts.get(symbol, Decimal("0"))),
                "mark_price": decimal_to_str(mark_price),
                "pending_cycles": 0,
                "reason": clip_reason,
            }
            _append_order_event(service, pending)
            update_cycle_order(pending)

            if side == "buy":
                dynamic_risk = build_risk_status(
                    service.paths.root,
                    snapshot={"timestamp": run_time, "nav": decimal_to_str(current_snapshot.nav)},
                )
                if dynamic_risk["blocked_new_orders"]:
                    append_rejection(pending, "; ".join(dynamic_risk["blocked_reasons"]), risk_event_type="order_rejected_risk_gate")
                    continue

            try:
                fill_price_estimate, fee_estimate, _ = _estimate_fill_values(
                    quantity=order_quantity,
                    mark_price=mark_price,
                    side=side,
                    fee_bps=execution_config.fee_bps,
                    slippage_bps=execution_config.slippage_bps,
                )
                stop_loss_override = None
                target_stop_loss_pct = target_stop_loss_pcts.get(symbol, Decimal("0"))
                if side == "buy" and target_stop_loss_pct > 0:
                    stop_loss_override = quantize_8(fill_price_estimate * (Decimal("1") - target_stop_loss_pct))
                provided_stop_loss = stop_loss_override
                if provided_stop_loss is None and current_position is not None:
                    provided_stop_loss = current_position.stop_loss
                day_open_nav = service.day_open_nav(datetime.fromisoformat(run_time).date()) or current_snapshot.nav
                risk_manager.validate_trade(
                    symbol=symbol,
                    side=side,
                    quantity=order_quantity,
                    price=fill_price_estimate,
                    cash_balance=service.load_account().cash_balance,
                    fee=fee_estimate,
                    current_position=current_position,
                    nav=current_snapshot.nav,
                    day_open_nav=day_open_nav,
                    stop_loss=risk_manager.resolve_stop_loss(side, fill_price_estimate, provided_stop_loss),
                    positions=current_positions,
                    marks=current_snapshot.marks,
                )
            except RiskViolation as exc:
                append_rejection(pending, str(exc), risk_event_type="order_rejected_risk_gate")
                continue

            refreshed_positions = service.load_positions()
            try_fill(
                pending,
                current_position=refreshed_positions.get(symbol),
                target_weight=target_weight,
            )

        snapshot_after = service.snapshot(timestamp=run_time, persist=True, price_overrides=price_map or None)
        risk_state = service.load_risk_state()
        starting_cooldown = int(risk_state.get("cooldown_remaining_cycles", 0))
        if starting_cooldown > 0:
            risk_state["cooldown_remaining_cycles"] = max(0, starting_cooldown - 1)

        if fill_rows and realized_pnl < 0:
            risk_state["consecutive_loss_count"] = int(risk_state.get("consecutive_loss_count", 0)) + 1
            risk_state["last_loss_at"] = run_time
        elif fill_rows and realized_pnl > 0:
            risk_state["consecutive_loss_count"] = 0
            risk_state["last_win_at"] = run_time

        if (
            fill_rows
            and realized_pnl < 0
            and risk_state["consecutive_loss_count"] >= risk_config.consecutive_loss_limit
            and risk_config.cooldown_cycles > 0
        ):
            risk_state["cooldown_remaining_cycles"] = max(
                int(risk_state.get("cooldown_remaining_cycles", 0)),
                risk_config.cooldown_cycles,
            )
            risk_state["cooldown_activated_at"] = run_time
            risk_state["cooldown_reason"] = (
                f"{risk_state['consecutive_loss_count']} consecutive losing execution cycle(s)"
            )
            _append_risk_event(
                service,
                {
                    "timestamp": run_time,
                    "execution_id": execution_id,
                    "type": "consecutive_loss_cooldown",
                    "status": "blocked",
                    "reason": risk_state["cooldown_reason"],
                    "details": {
                        "cooldown_remaining_cycles": risk_state["cooldown_remaining_cycles"],
                        "consecutive_loss_limit": risk_config.consecutive_loss_limit,
                    },
                },
            )

        risk_state["last_execution_realized_pnl"] = decimal_to_str(realized_pnl)
        risk_state["updated_at"] = run_time
        service.save_risk_state(risk_state)

        final_risk_status = build_risk_status(
            service.paths.root,
            snapshot={"timestamp": run_time, "nav": decimal_to_str(snapshot_after.nav)},
        )
        entry = {
            "execution_id": execution_id,
            "timestamp": run_time,
            "source": source,
            "decision_source": str(signal_entry.get("decision_source", "signals")),
            "decision_id": str(signal_entry.get("decision_id", "")),
            "signal_timestamp": str(signal_entry.get("timestamp", "")),
            "signal_summary": str(signal_entry.get("summary", "")),
            "market_timestamp": str(signal_entry.get("market_timestamp", "")),
            "status": "alert" if rejection_rows else ("watch" if cancel_rows else "ok"),
            "targets_considered": len(target_weights),
            "open_orders_before": len(open_orders_before),
            "open_orders_after": len(
                [
                    row
                    for row in _current_order_book(service).values()
                    if str(row.get("status", "")) in OPEN_ORDER_STATUSES
                ]
            ),
            "filled_orders": len([row for row in cycle_order_rows.values() if row["status"] == "filled"]),
            "partial_orders": len([row for row in cycle_order_rows.values() if row["status"] == "partial"]),
            "pending_orders": len([row for row in cycle_order_rows.values() if row["status"] == "pending"]),
            "canceled_orders": len(cancel_rows),
            "rejected_orders": len(rejection_rows),
            "fills_count": len(fill_rows),
            "fill_notional_total": decimal_to_str(
                sum((to_decimal(row.get("fill_quantity", "0")) * to_decimal(row.get("avg_fill_price", "0")) for row in fill_rows), Decimal("0"))
            ),
            "fees_total": decimal_to_str(fees_total),
            "slippage_total": decimal_to_str(slippage_total),
            "realized_pnl": decimal_to_str(realized_pnl),
            "nav_before": decimal_to_str(snapshot_before.nav),
            "nav_after": decimal_to_str(snapshot_after.nav),
            "summary": (
                f"fills={len(fill_rows)} partial={len([row for row in cycle_order_rows.values() if row['status'] == 'partial'])} "
                + f"rejected={len(rejection_rows)} canceled={len(cancel_rows)} nav={decimal_to_str(snapshot_after.nav)}"
            ),
            "orders": list(sorted(cycle_order_rows.values(), key=lambda row: (str(row["symbol"]), str(row["order_id"])))),
            "rejections": rejection_rows,
            "decision_adjustments": list(signal_entry.get("ds_adjustments", []))
            if isinstance(signal_entry.get("ds_adjustments"), list)
            else [],
            "risk_status": final_risk_status,
        }
        append_jsonl(service.paths.execution_runs, entry)
        return ExecutionCycleResult(entry=entry)
