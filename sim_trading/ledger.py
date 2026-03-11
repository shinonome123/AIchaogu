from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from sim_trading.models import (
    AccountState,
    ExecutionConfig,
    Position,
    RiskConfig,
    Snapshot,
    TradeResult,
    ValidationConfig,
    decimal_to_money,
    decimal_to_str,
    normalize_symbol,
    now_iso,
    quantize_8,
    to_decimal,
)
from sim_trading.risk import RiskManager
from sim_trading.storage import (
    EQUITY_HEADERS,
    TRADE_HEADERS,
    StoragePaths,
    append_jsonl,
    append_csv_row,
    ensure_csv,
    ensure_json,
    read_csv_rows,
    read_last_jsonl,
    read_json,
    write_json,
)

LEGACY_SYNTHETIC_MODE = "synthetic_seed_units"
NORMALIZED_NOTIONAL_MODE = "normalized_seed_notional"


def _seed_default_initial_capital(payload: dict[str, Any]) -> Decimal:
    account_payload = payload.get("account", {}) if isinstance(payload, dict) else {}
    positions_payload = payload.get("positions", []) if isinstance(payload, dict) else []
    starting_cash = to_decimal(account_payload.get("cash_balance", "0"))
    starting_positions = Decimal("0")
    if isinstance(positions_payload, list):
        for item in positions_payload:
            if not isinstance(item, dict):
                continue
            quantity = to_decimal(item.get("quantity", "0"))
            average_entry = to_decimal(item.get("average_entry_price", item.get("last_price", "0")))
            starting_positions += quantity * average_entry
    return quantize_8(starting_cash + starting_positions)


class LedgerService:
    def __init__(self, state_dir: Path | str) -> None:
        self.paths = StoragePaths(Path(state_dir))
        self.paths.ensure_dirs()

    def initialize_from_seed(self, seed_path: Path | str) -> list[str]:
        payload = read_json(Path(seed_path))
        if payload is None:
            raise FileNotFoundError(f"seed file not found: {seed_path}")

        created: list[str] = []
        default_initial_capital = _seed_default_initial_capital(payload)
        account_payload = dict(payload["account"])
        account_payload.setdefault("realized_pnl_total", "0")
        account_payload.setdefault("updated_at", account_payload["created_at"])
        account_payload.setdefault("source_note", payload.get("source_note", ""))
        account_payload.setdefault("metadata", {})
        if not isinstance(account_payload["metadata"], dict):
            account_payload["metadata"] = {}
        if (
            account_payload["metadata"].get("seed_migration_mode") == "synthetic_single_unit_positions"
            or any(
                str(item.get("metadata", {}).get("seed_basis", "")) == "synthetic_single_unit_from_notional"
                for item in payload.get("positions", [])
                if isinstance(item, dict)
            )
        ):
            account_payload["metadata"].setdefault("position_mode", LEGACY_SYNTHETIC_MODE)
            account_payload["metadata"].setdefault("position_mode_source_note", payload.get("source_note", ""))

        if ensure_json(self.paths.account, account_payload):
            created.append(str(self.paths.account))

        config_payload = {
            "risk": RiskConfig.from_dict(payload.get("risk", {})).to_dict(),
            "execution": ExecutionConfig.from_dict(payload.get("execution", {})).to_dict(),
            "validation": ValidationConfig.from_dict(
                payload.get("validation", {}),
                default_initial_capital=default_initial_capital,
            ).to_dict(),
            "strategy": payload.get("strategy", {}),
            "seed_source_path": payload.get("source_path", ""),
            "seed_source_note": payload.get("source_note", ""),
            "position_mode": account_payload["metadata"].get("position_mode", "standard_positions"),
        }
        if ensure_json(self.paths.config, config_payload):
            created.append(str(self.paths.config))

        if ensure_json(self.paths.positions, payload["positions"]):
            created.append(str(self.paths.positions))

        if ensure_json(
            self.paths.market_prices,
            {
                item["symbol"]: {
                    "price": item.get("last_price", item["average_entry_price"]),
                    "timestamp": item.get("updated_at", item["opened_at"]),
                }
                for item in payload["positions"]
            },
        ):
            created.append(str(self.paths.market_prices))

        if ensure_csv(self.paths.trades, TRADE_HEADERS):
            created.append(str(self.paths.trades))

        if ensure_csv(self.paths.equity_curve, EQUITY_HEADERS):
            created.append(str(self.paths.equity_curve))

        if ensure_json(self.paths.risk_state, self.default_risk_state(timestamp=account_payload["created_at"])):
            created.append(str(self.paths.risk_state))

        if not read_csv_rows(self.paths.equity_curve):
            timestamp = account_payload["created_at"]
            self.snapshot(timestamp=timestamp, persist=True, price_overrides={})
            created.append(str(self.paths.equity_curve))

        return list(dict.fromkeys(created))

    def load_account(self) -> AccountState:
        payload = read_json(self.paths.account)
        if payload is None:
            raise FileNotFoundError("state not initialized: account.json is missing")
        return AccountState.from_dict(payload)

    def save_account(self, account: AccountState) -> None:
        write_json(self.paths.account, account.to_dict())

    def load_positions(self) -> dict[str, Position]:
        payload = read_json(self.paths.positions, default=[])
        return {normalize_symbol(item["symbol"]): Position.from_dict(item) for item in payload}

    def save_positions(self, positions: dict[str, Position]) -> None:
        payload = [positions[key].to_dict() for key in sorted(positions)]
        write_json(self.paths.positions, payload)

    def load_market_prices(self) -> dict[str, dict[str, str]]:
        return read_json(self.paths.market_prices, default={})

    def save_market_prices(self, prices: dict[str, dict[str, str]]) -> None:
        write_json(self.paths.market_prices, prices)

    def load_config_payload(self) -> dict[str, Any]:
        payload = read_json(self.paths.config)
        if payload is None:
            raise FileNotFoundError("state not initialized: config.json is missing")
        if not isinstance(payload, dict):
            raise ValueError("config.json must contain a JSON object")
        return payload

    def save_config_payload(self, payload: dict[str, Any]) -> None:
        write_json(self.paths.config, payload)

    def load_risk_config(self) -> RiskConfig:
        payload = self.load_config_payload()
        return RiskConfig.from_dict(payload.get("risk", {}))

    def load_execution_config(self) -> ExecutionConfig:
        payload = self.load_config_payload()
        return ExecutionConfig.from_dict(payload.get("execution", {}))

    def load_validation_config(self) -> ValidationConfig:
        payload = self.load_config_payload()
        default_initial_capital = self.build_snapshot(timestamp=now_iso(), price_overrides=None).nav
        return ValidationConfig.from_dict(payload.get("validation", {}), default_initial_capital=default_initial_capital)

    def default_risk_state(self, *, timestamp: str | None = None) -> dict[str, Any]:
        return {
            "kill_switch_enabled": False,
            "kill_switch_reason": "",
            "consecutive_loss_count": 0,
            "cooldown_remaining_cycles": 0,
            "cooldown_activated_at": None,
            "cooldown_reason": "",
            "last_execution_realized_pnl": "0",
            "last_loss_at": None,
            "last_win_at": None,
            "last_circuit_breaker_event": None,
            "updated_at": timestamp or now_iso(),
        }

    def load_risk_state(self) -> dict[str, Any]:
        payload = read_json(self.paths.risk_state)
        if not isinstance(payload, dict):
            payload = self.default_risk_state()
            write_json(self.paths.risk_state, payload)
            return payload
        default_payload = self.default_risk_state(timestamp=str(payload.get("updated_at", "")) or now_iso())
        default_payload.update(payload)
        return default_payload

    def save_risk_state(self, payload: dict[str, Any]) -> None:
        default_payload = self.default_risk_state(timestamp=str(payload.get("updated_at", "")) or now_iso())
        default_payload.update(payload)
        write_json(self.paths.risk_state, default_payload)

    def _merged_marks(self, positions: dict[str, Position], overrides: dict[str, Decimal] | None = None) -> dict[str, Decimal]:
        marks: dict[str, Decimal] = {}
        market_prices = self.load_market_prices()
        for symbol, position in positions.items():
            stored = market_prices.get(symbol, {})
            marks[symbol] = to_decimal(stored.get("price", position.last_price))
        if overrides:
            for symbol, price in overrides.items():
                marks[normalize_symbol(symbol)] = quantize_8(price)
        return marks

    def normalization_cutoff(self) -> datetime | None:
        mode = self.position_mode_status()
        if not mode["is_normalized"] or not mode["normalized_at"]:
            return None
        return datetime.fromisoformat(str(mode["normalized_at"]))

    def normalized_equity_rows(self) -> list[dict[str, str]]:
        rows = read_csv_rows(self.paths.equity_curve)
        cutoff = self.normalization_cutoff()
        if cutoff is None:
            return rows
        return [row for row in rows if datetime.fromisoformat(row["timestamp"]) >= cutoff]

    def _existing_navs(self) -> list[Decimal]:
        return [to_decimal(row["nav"]) for row in self.normalized_equity_rows()]

    def _day_open_nav(self, target_day: date) -> Decimal | None:
        for row in self.normalized_equity_rows():
            row_dt = datetime.fromisoformat(row["timestamp"])
            if row_dt.date() == target_day:
                return to_decimal(row["nav"])
        return None

    def day_open_nav(self, target_day: date) -> Decimal | None:
        return self._day_open_nav(target_day)

    def _snapshot_to_dict(self, snapshot: Snapshot) -> dict[str, Any]:
        return {
            "timestamp": snapshot.timestamp,
            "cash_balance": decimal_to_str(snapshot.cash_balance),
            "positions_market_value": decimal_to_str(snapshot.positions_market_value),
            "nav": decimal_to_str(snapshot.nav),
            "realized_pnl_total": decimal_to_str(snapshot.realized_pnl_total),
            "unrealized_pnl_total": decimal_to_str(snapshot.unrealized_pnl_total),
            "drawdown_pct": decimal_to_str(snapshot.drawdown_pct),
            "breached_stop_losses": list(snapshot.breached_stop_losses),
            "marks": {symbol: decimal_to_str(price) for symbol, price in snapshot.marks.items()},
        }

    def position_mode_status(self) -> dict[str, Any]:
        account = self.load_account()
        positions = self.load_positions()
        metadata = account.metadata if isinstance(account.metadata, dict) else {}
        pending_symbols = [
            symbol
            for symbol, position in positions.items()
            if str(position.metadata.get("seed_basis", "")) == "synthetic_single_unit_from_notional"
            and not bool(position.metadata.get("normalized_from_seed_notional"))
        ]
        stored_mode = str(metadata.get("position_mode", "")).strip()
        if stored_mode:
            mode = stored_mode
        elif metadata.get("seed_migration_mode") == "synthetic_single_unit_positions" or pending_symbols:
            mode = LEGACY_SYNTHETIC_MODE
        else:
            mode = "standard_positions"
        return {
            "mode": mode,
            "is_normalized": mode == NORMALIZED_NOTIONAL_MODE,
            "normalized_at": str(metadata.get("position_normalized_at", "")).strip() or None,
            "source_note": str(metadata.get("position_mode_source_note", account.source_note)).strip(),
            "pending_symbols": pending_symbols,
            "pending_count": len(pending_symbols),
            "requires_normalization": bool(pending_symbols) and mode != NORMALIZED_NOTIONAL_MODE,
        }

    def _reference_prices_for_positions(
        self,
        positions: dict[str, Position],
        *,
        price_overrides: dict[str, Decimal] | None = None,
    ) -> tuple[dict[str, Decimal], dict[str, dict[str, str]]]:
        reference_prices: dict[str, Decimal] = {}
        reference_meta: dict[str, dict[str, str]] = {}

        market_prices = self.load_market_prices()
        for symbol in positions:
            stored = market_prices.get(symbol)
            if not stored or "price" not in stored:
                continue
            reference_prices[symbol] = quantize_8(to_decimal(stored["price"]))
            reference_meta[symbol] = {
                "reference_type": "market_prices",
                "reference_source": "market_prices.json",
                "reference_timestamp": str(stored.get("timestamp", "")),
            }

        latest_market_feed = read_last_jsonl(self.paths.market_feed)
        if isinstance(latest_market_feed, dict):
            latest_prices = latest_market_feed.get("prices", {})
            if isinstance(latest_prices, dict):
                for symbol in positions:
                    payload = latest_prices.get(symbol)
                    if not isinstance(payload, dict) or "price" not in payload:
                        continue
                    reference_prices[symbol] = quantize_8(to_decimal(payload["price"]))
                    reference_meta[symbol] = {
                        "reference_type": "market_feed",
                        "reference_source": str(payload.get("source", latest_market_feed.get("source", "market-feed"))),
                        "reference_timestamp": str(payload.get("timestamp", latest_market_feed.get("timestamp", ""))),
                    }

        for symbol, price in (price_overrides or {}).items():
            normalized_symbol = normalize_symbol(symbol)
            if normalized_symbol not in positions:
                continue
            reference_prices[normalized_symbol] = quantize_8(price)
            reference_meta[normalized_symbol] = {
                "reference_type": "override",
                "reference_source": "cli",
                "reference_timestamp": "",
            }

        return reference_prices, reference_meta

    def normalize_seed_positions(
        self,
        *,
        timestamp: str | None = None,
        price_overrides: dict[str, Decimal] | None = None,
        source_note: str = (
            "Normalized synthetic seed-unit positions into carrying-notional market-based quantities. "
            "Open positions keep their remaining notional and reset unrealized PnL from the normalization mark."
        ),
    ) -> dict[str, Any]:
        normalize_time = timestamp or now_iso()
        account = self.load_account()
        config_payload = self.load_config_payload()
        positions = self.load_positions()
        candidates = {
            symbol: position
            for symbol, position in positions.items()
            if str(position.metadata.get("seed_basis", "")) == "synthetic_single_unit_from_notional"
            and not bool(position.metadata.get("normalized_from_seed_notional"))
        }
        if not candidates:
            raise ValueError("no synthetic seed positions require normalization")
        before_mode = self.position_mode_status()

        reference_prices, reference_meta = self._reference_prices_for_positions(
            candidates,
            price_overrides=price_overrides,
        )
        missing_symbols = sorted(symbol for symbol in candidates if symbol not in reference_prices)
        if missing_symbols:
            raise ValueError(
                "missing reference prices for normalization: "
                + ", ".join(missing_symbols)
                + ". Fetch market data first or pass --price SYMBOL=PRICE."
            )

        before_snapshot = self.build_snapshot(timestamp=normalize_time, price_overrides=reference_prices)
        before_account = account.to_dict()
        before_positions = [positions[symbol].to_dict() for symbol in sorted(positions)]
        normalized_rows: list[dict[str, str]] = []

        for symbol in sorted(candidates):
            position = candidates[symbol]
            reference_price = reference_prices[symbol]
            if reference_price <= 0:
                raise ValueError(f"reference price for {symbol} must be positive")
            carrying_notional = quantize_8(position.quantity * position.average_entry_price)
            normalized_quantity = quantize_8(carrying_notional / reference_price)
            if normalized_quantity <= 0:
                raise ValueError(f"normalized quantity for {symbol} must be positive")

            original_stop = position.stop_loss
            normalized_stop: Decimal | None = None
            if original_stop is not None and position.average_entry_price > 0:
                stop_ratio = quantize_8(original_stop / position.average_entry_price)
                normalized_stop = quantize_8(reference_price * stop_ratio)

            original_quantity = position.quantity
            original_average = position.average_entry_price
            original_last = position.last_price
            position.quantity = normalized_quantity
            position.average_entry_price = reference_price
            position.last_price = reference_price
            position.stop_loss = normalized_stop
            position.updated_at = normalize_time

            metadata = dict(position.metadata)
            metadata["normalized_from_seed_notional"] = True
            metadata["normalized_from_seed_basis"] = str(metadata.get("seed_basis", ""))
            metadata["normalized_at"] = normalize_time
            metadata["normalization_source_note"] = source_note
            metadata["normalization_reference_price"] = decimal_to_str(reference_price)
            metadata["normalization_reference_type"] = reference_meta[symbol]["reference_type"]
            metadata["normalization_reference_source"] = reference_meta[symbol]["reference_source"]
            metadata["normalization_reference_timestamp"] = reference_meta[symbol]["reference_timestamp"]
            metadata["normalization_carrying_notional"] = decimal_to_str(carrying_notional)
            metadata["pre_normalization_quantity"] = decimal_to_str(original_quantity)
            metadata["pre_normalization_average_entry_price"] = decimal_to_str(original_average)
            metadata["pre_normalization_last_price"] = decimal_to_str(original_last)
            if original_stop is not None:
                metadata["pre_normalization_stop_loss"] = decimal_to_str(original_stop)
            position.metadata = metadata

            normalized_rows.append(
                {
                    "symbol": symbol,
                    "carrying_notional": decimal_to_str(carrying_notional),
                    "previous_quantity": decimal_to_str(original_quantity),
                    "normalized_quantity": decimal_to_str(normalized_quantity),
                    "previous_average_entry_price": decimal_to_str(original_average),
                    "normalized_average_entry_price": decimal_to_str(reference_price),
                    "previous_stop_loss": decimal_to_str(original_stop) if original_stop is not None else "",
                    "normalized_stop_loss": decimal_to_str(normalized_stop) if normalized_stop is not None else "",
                    **reference_meta[symbol],
                }
            )

        account_metadata = dict(account.metadata if isinstance(account.metadata, dict) else {})
        account_metadata["position_mode"] = NORMALIZED_NOTIONAL_MODE
        account_metadata["position_normalized_at"] = normalize_time
        account_metadata["position_mode_source_note"] = source_note
        account_metadata["position_normalized_symbols"] = [row["symbol"] for row in normalized_rows]
        account_metadata["position_normalization_version"] = 1
        account.metadata = account_metadata
        account.updated_at = normalize_time

        config_payload["position_mode"] = NORMALIZED_NOTIONAL_MODE
        config_payload["position_normalization"] = {
            "normalized_at": normalize_time,
            "source_note": source_note,
            "symbols": [row["symbol"] for row in normalized_rows],
        }

        self.save_account(account)
        self.save_positions(positions)
        self.save_config_payload(config_payload)
        after_snapshot = self.snapshot(
            timestamp=normalize_time,
            persist=True,
            price_overrides=reference_prices,
        )

        audit_entry = {
            "timestamp": normalize_time,
            "source_note": source_note,
            "mode_before": before_mode["mode"],
            "mode_after": NORMALIZED_NOTIONAL_MODE,
            "normalized_count": len(normalized_rows),
            "normalized_positions": normalized_rows,
            "before": {
                "account": before_account,
                "positions": before_positions,
                "snapshot": self._snapshot_to_dict(before_snapshot),
            },
            "after": {
                "account": account.to_dict(),
                "positions": [positions[symbol].to_dict() for symbol in sorted(positions)],
                "snapshot": self._snapshot_to_dict(after_snapshot),
            },
        }
        append_jsonl(self.paths.normalization_audit, audit_entry)
        return {
            "timestamp": normalize_time,
            "source_note": source_note,
            "normalized_positions": normalized_rows,
            "before_snapshot": self._snapshot_to_dict(before_snapshot),
            "after_snapshot": self._snapshot_to_dict(after_snapshot),
            "audit_path": str(self.paths.normalization_audit),
        }

    def build_snapshot(self, *, timestamp: str, price_overrides: dict[str, Decimal] | None = None) -> Snapshot:
        account = self.load_account()
        positions = self.load_positions()
        marks = self._merged_marks(positions, overrides=price_overrides)
        positions_market_value = Decimal("0")
        unrealized_pnl_total = Decimal("0")
        for symbol, position in positions.items():
            mark = marks.get(symbol, position.last_price)
            positions_market_value += position.market_value(mark)
            unrealized_pnl_total += position.unrealized_pnl(mark)

        nav = quantize_8(account.cash_balance + positions_market_value)
        existing_navs = self._existing_navs()
        peak_nav = max(existing_navs + [nav]) if existing_navs or nav else nav
        drawdown_pct = Decimal("0")
        if peak_nav > 0:
            drawdown_pct = quantize_8((nav / peak_nav) - Decimal("1"))

        risk = RiskManager(self.load_risk_config())
        breached = risk.breached_stop_losses(positions, marks)

        return Snapshot(
            timestamp=timestamp,
            cash_balance=quantize_8(account.cash_balance),
            positions_market_value=quantize_8(positions_market_value),
            nav=nav,
            realized_pnl_total=quantize_8(account.realized_pnl_total),
            unrealized_pnl_total=quantize_8(unrealized_pnl_total),
            drawdown_pct=drawdown_pct,
            breached_stop_losses=breached,
            marks=marks,
        )

    def snapshot(
        self,
        *,
        timestamp: str | None = None,
        persist: bool = True,
        price_overrides: dict[str, Decimal] | None = None,
    ) -> Snapshot:
        snapshot_time = timestamp or now_iso()
        snapshot = self.build_snapshot(timestamp=snapshot_time, price_overrides=price_overrides)
        if not persist:
            return snapshot

        market_prices = self.load_market_prices()
        for symbol, price in snapshot.marks.items():
            market_prices[symbol] = {"price": decimal_to_str(price), "timestamp": snapshot_time}

        positions = self.load_positions()
        for symbol, position in positions.items():
            if symbol in snapshot.marks:
                position.last_price = snapshot.marks[symbol]
                position.updated_at = snapshot_time
        self.save_positions(positions)
        self.save_market_prices(market_prices)

        append_csv_row(
            self.paths.equity_curve,
            EQUITY_HEADERS,
            {
                "timestamp": snapshot.timestamp,
                "cash_balance": decimal_to_str(snapshot.cash_balance),
                "positions_market_value": decimal_to_str(snapshot.positions_market_value),
                "nav": decimal_to_str(snapshot.nav),
                "realized_pnl_total": decimal_to_str(snapshot.realized_pnl_total),
                "unrealized_pnl_total": decimal_to_str(snapshot.unrealized_pnl_total),
                "drawdown_pct": decimal_to_str(snapshot.drawdown_pct),
                "breached_stop_losses": ",".join(snapshot.breached_stop_losses),
                "marks_json": json.dumps({k: decimal_to_str(v) for k, v in snapshot.marks.items()}, sort_keys=True),
            },
        )
        return snapshot

    def record_trade(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        fee: Decimal = Decimal("0"),
        timestamp: str | None = None,
        strategy: str = "manual",
        note: str = "",
        stop_loss: Decimal | None = None,
        enforce_risk_checks: bool = True,
    ) -> TradeResult:
        trade_time = timestamp or now_iso()
        symbol = normalize_symbol(symbol)
        side = side.lower()
        quantity = quantize_8(quantity)
        price = quantize_8(price)
        fee = quantize_8(fee)
        if side not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")

        account = self.load_account()
        positions = self.load_positions()
        current_position = positions.get(symbol)
        pre_trade_snapshot = self.build_snapshot(
            timestamp=trade_time,
            price_overrides={symbol: price},
        )
        day_open_nav = self._day_open_nav(datetime.fromisoformat(trade_time).date()) or pre_trade_snapshot.nav
        risk_config = self.load_risk_config()
        risk_manager = RiskManager(risk_config)
        resolved_stop_loss = risk_manager.resolve_stop_loss(side, price, stop_loss)
        if enforce_risk_checks:
            risk_manager.validate_trade(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                cash_balance=account.cash_balance,
                fee=fee,
                current_position=current_position,
                nav=pre_trade_snapshot.nav,
                day_open_nav=day_open_nav,
                stop_loss=resolved_stop_loss,
                positions=positions,
                marks=pre_trade_snapshot.marks,
            )

        realized_pnl = Decimal("0")
        notional = quantize_8(quantity * price)
        if side == "buy":
            cash_after = quantize_8(account.cash_balance - notional - fee)
            if current_position:
                new_qty = quantize_8(current_position.quantity + quantity)
                total_cost = (current_position.average_entry_price * current_position.quantity) + notional
                current_position.average_entry_price = quantize_8(total_cost / new_qty)
                current_position.quantity = new_qty
                current_position.last_price = price
                current_position.updated_at = trade_time
                if resolved_stop_loss is not None:
                    current_position.stop_loss = resolved_stop_loss
            else:
                positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantize_8(quantity),
                    average_entry_price=quantize_8(price),
                    last_price=quantize_8(price),
                    stop_loss=resolved_stop_loss,
                    opened_at=trade_time,
                    updated_at=trade_time,
                    metadata={},
                )
            position_qty_after = positions[symbol].quantity
        else:
            assert current_position is not None
            realized_pnl = quantize_8(((price - current_position.average_entry_price) * quantity) - fee)
            cash_after = quantize_8(account.cash_balance + notional - fee)
            remaining_qty = quantize_8(current_position.quantity - quantity)
            if remaining_qty > 0:
                current_position.quantity = remaining_qty
                current_position.last_price = price
                current_position.updated_at = trade_time
                position_qty_after = current_position.quantity
            else:
                positions.pop(symbol)
                position_qty_after = Decimal("0")

        account.cash_balance = cash_after
        account.realized_pnl_total = quantize_8(account.realized_pnl_total + realized_pnl)
        account.updated_at = trade_time
        self.save_account(account)
        self.save_positions(positions)

        post_snapshot = self.snapshot(
            timestamp=trade_time,
            persist=True,
            price_overrides={symbol: price},
        )

        trade_result = TradeResult(
            trade_id=f"TRD-{uuid4().hex[:12].upper()}",
            timestamp=trade_time,
            symbol=symbol,
            side=side,
            quantity=quantize_8(quantity),
            price=quantize_8(price),
            fee=quantize_8(fee),
            realized_pnl=realized_pnl,
            cash_after=cash_after,
            position_qty_after=position_qty_after,
            nav_after=post_snapshot.nav,
            applied_stop_loss=resolved_stop_loss,
        )
        append_csv_row(
            self.paths.trades,
            TRADE_HEADERS,
            {
                "trade_id": trade_result.trade_id,
                "timestamp": trade_result.timestamp,
                "symbol": trade_result.symbol,
                "side": trade_result.side,
                "quantity": decimal_to_str(trade_result.quantity),
                "price": decimal_to_str(trade_result.price),
                "notional": decimal_to_str(notional),
                "fee": decimal_to_str(trade_result.fee),
                "strategy": strategy,
                "note": note,
                "stop_loss": decimal_to_str(trade_result.applied_stop_loss) if trade_result.applied_stop_loss else "",
                "realized_pnl": decimal_to_str(trade_result.realized_pnl),
                "cash_after": decimal_to_str(trade_result.cash_after),
                "position_qty_after": decimal_to_str(trade_result.position_qty_after),
                "nav_after": decimal_to_str(trade_result.nav_after),
            },
        )
        return trade_result

    def status_lines(self, snapshot: Snapshot) -> list[str]:
        positions = self.load_positions()
        mode = self.position_mode_status()
        lines = [
            f"Timestamp: {snapshot.timestamp}",
            f"Position Mode: {mode['mode']}",
            f"Cash: {decimal_to_money(snapshot.cash_balance)}",
            f"Market Value: {decimal_to_money(snapshot.positions_market_value)}",
            f"NAV: {decimal_to_money(snapshot.nav)}",
            f"Realized PnL: {decimal_to_money(snapshot.realized_pnl_total)}",
            f"Unrealized PnL: {decimal_to_money(snapshot.unrealized_pnl_total)}",
            f"Drawdown: {snapshot.drawdown_pct:.2%}",
        ]
        if mode["is_normalized"]:
            lines.append(f"Normalized At: {mode['normalized_at'] or 'unknown'}")
        elif mode["requires_normalization"]:
            lines.append("Normalization Pending: yes")
        if snapshot.breached_stop_losses:
            lines.append(f"Stop-loss alerts: {', '.join(snapshot.breached_stop_losses)}")
        else:
            lines.append("Stop-loss alerts: none")
        if not positions:
            lines.append("Positions: none")
            return lines

        lines.append("Positions:")
        for symbol in sorted(positions):
            position = positions[symbol]
            mark = snapshot.marks.get(symbol, position.last_price)
            lines.append(
                "  "
                + f"{symbol}: qty={decimal_to_str(position.quantity)} avg={decimal_to_money(position.average_entry_price)} "
                + f"mark={decimal_to_money(mark)} mv={decimal_to_money(position.market_value(mark))} "
                + f"uPnL={decimal_to_money(position.unrealized_pnl(mark))} "
                + f"stop={decimal_to_money(position.stop_loss) if position.stop_loss is not None else 'n/a'}"
            )
        return lines
