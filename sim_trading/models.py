from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

DECIMAL_8 = Decimal("0.00000001")
DECIMAL_2 = Decimal("0.01")


def to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def quantize_8(value: Any) -> Decimal:
    return to_decimal(value).quantize(DECIMAL_8, rounding=ROUND_HALF_UP)


def quantize_2(value: Any) -> Decimal:
    return to_decimal(value).quantize(DECIMAL_2, rounding=ROUND_HALF_UP)


def decimal_to_str(value: Any) -> str:
    normalized = quantize_8(value).normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def decimal_to_money(value: Any) -> str:
    return format(quantize_2(value), "f")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


@dataclass
class Position:
    symbol: str
    quantity: Decimal
    average_entry_price: Decimal
    last_price: Decimal
    stop_loss: Decimal | None
    opened_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Position":
        return cls(
            symbol=normalize_symbol(payload["symbol"]),
            quantity=to_decimal(payload["quantity"]),
            average_entry_price=to_decimal(payload["average_entry_price"]),
            last_price=to_decimal(payload.get("last_price", payload["average_entry_price"])),
            stop_loss=to_decimal(payload["stop_loss"]) if payload.get("stop_loss") is not None else None,
            opened_at=payload["opened_at"],
            updated_at=payload.get("updated_at", payload["opened_at"]),
            metadata=payload.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": decimal_to_str(self.quantity),
            "average_entry_price": decimal_to_str(self.average_entry_price),
            "last_price": decimal_to_str(self.last_price),
            "stop_loss": decimal_to_str(self.stop_loss) if self.stop_loss is not None else None,
            "opened_at": self.opened_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    def market_value(self, price: Decimal | None = None) -> Decimal:
        mark = price if price is not None else self.last_price
        return quantize_8(self.quantity * mark)

    def unrealized_pnl(self, price: Decimal | None = None) -> Decimal:
        mark = price if price is not None else self.last_price
        return quantize_8((mark - self.average_entry_price) * self.quantity)


@dataclass
class AccountState:
    account_id: str
    base_currency: str
    cash_balance: Decimal
    realized_pnl_total: Decimal
    created_at: str
    updated_at: str
    source_note: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AccountState":
        return cls(
            account_id=payload["account_id"],
            base_currency=payload["base_currency"],
            cash_balance=to_decimal(payload["cash_balance"]),
            realized_pnl_total=to_decimal(payload.get("realized_pnl_total", "0")),
            created_at=payload["created_at"],
            updated_at=payload.get("updated_at", payload["created_at"]),
            source_note=payload.get("source_note", ""),
            metadata=payload.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "base_currency": self.base_currency,
            "cash_balance": decimal_to_str(self.cash_balance),
            "realized_pnl_total": decimal_to_str(self.realized_pnl_total),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_note": self.source_note,
            "metadata": self.metadata,
        }


@dataclass
class RiskConfig:
    max_position_size_pct: Decimal
    daily_loss_cap_pct: Decimal
    default_stop_loss_pct: Decimal
    max_gross_exposure_pct: Decimal = Decimal("1")
    max_concurrent_positions: int = 999
    require_stop_loss: bool = True
    consecutive_loss_limit: int = 3
    cooldown_cycles: int = 2

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RiskConfig":
        max_position = payload.get("max_position_weight_pct", payload.get("max_position_size_pct", "0.25"))
        if payload.get("daily_loss_circuit_breaker_pct") is not None:
            daily_loss_cap = abs(to_decimal(payload["daily_loss_circuit_breaker_pct"]))
        else:
            daily_loss_cap = abs(to_decimal(payload.get("daily_loss_cap_pct", "0.03")))
        return cls(
            max_position_size_pct=to_decimal(max_position),
            daily_loss_cap_pct=daily_loss_cap,
            default_stop_loss_pct=to_decimal(payload.get("default_stop_loss_pct", "0.05")),
            max_gross_exposure_pct=to_decimal(payload.get("max_gross_exposure_pct", "1")),
            max_concurrent_positions=max(1, int(payload.get("max_concurrent_positions", 999))),
            require_stop_loss=bool(payload.get("require_stop_loss", True)),
            consecutive_loss_limit=max(1, int(payload.get("consecutive_loss_limit", 3))),
            cooldown_cycles=max(0, int(payload.get("loss_cooldown_cycles", payload.get("cooldown_cycles", 2)))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_position_size_pct": decimal_to_str(self.max_position_size_pct),
            "max_position_weight_pct": decimal_to_str(self.max_position_size_pct),
            "daily_loss_cap_pct": decimal_to_str(self.daily_loss_cap_pct),
            "daily_loss_circuit_breaker_pct": decimal_to_str(-self.daily_loss_cap_pct),
            "default_stop_loss_pct": decimal_to_str(self.default_stop_loss_pct),
            "max_gross_exposure_pct": decimal_to_str(self.max_gross_exposure_pct),
            "max_concurrent_positions": self.max_concurrent_positions,
            "require_stop_loss": self.require_stop_loss,
            "consecutive_loss_limit": self.consecutive_loss_limit,
            "loss_cooldown_cycles": self.cooldown_cycles,
        }

    @property
    def max_position_weight_pct(self) -> Decimal:
        return self.max_position_size_pct

    @property
    def daily_loss_circuit_breaker_pct(self) -> Decimal:
        return -self.daily_loss_cap_pct


@dataclass
class ExecutionConfig:
    fee_bps: Decimal
    slippage_bps: Decimal
    min_order_notional: Decimal
    partial_fill_ratio: Decimal
    partial_fill_threshold_pct: Decimal
    cancel_pending_after_cycles: int
    auto_run_signals: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExecutionConfig":
        return cls(
            fee_bps=to_decimal(payload.get("fee_bps", "10")),
            slippage_bps=to_decimal(payload.get("slippage_bps", "5")),
            min_order_notional=to_decimal(payload.get("min_order_notional", "5")),
            partial_fill_ratio=to_decimal(payload.get("partial_fill_ratio", "0.65")),
            partial_fill_threshold_pct=to_decimal(payload.get("partial_fill_threshold_pct", "0.12")),
            cancel_pending_after_cycles=max(1, int(payload.get("cancel_pending_after_cycles", 2))),
            auto_run_signals=bool(payload.get("auto_run_signals", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fee_bps": decimal_to_str(self.fee_bps),
            "slippage_bps": decimal_to_str(self.slippage_bps),
            "min_order_notional": decimal_to_str(self.min_order_notional),
            "partial_fill_ratio": decimal_to_str(self.partial_fill_ratio),
            "partial_fill_threshold_pct": decimal_to_str(self.partial_fill_threshold_pct),
            "cancel_pending_after_cycles": self.cancel_pending_after_cycles,
            "auto_run_signals": self.auto_run_signals,
        }


@dataclass
class ValidationConfig:
    initial_capital: Decimal
    lookback_points: int
    step_points: int
    min_snapshots: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, default_initial_capital: Decimal) -> "ValidationConfig":
        return cls(
            initial_capital=to_decimal(payload.get("initial_capital", decimal_to_str(default_initial_capital))),
            lookback_points=max(2, int(payload.get("lookback_points", 6))),
            step_points=max(1, int(payload.get("step_points", 1))),
            min_snapshots=max(3, int(payload.get("min_snapshots", 8))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_capital": decimal_to_str(self.initial_capital),
            "lookback_points": self.lookback_points,
            "step_points": self.step_points,
            "min_snapshots": self.min_snapshots,
        }


@dataclass
class Snapshot:
    timestamp: str
    cash_balance: Decimal
    positions_market_value: Decimal
    nav: Decimal
    realized_pnl_total: Decimal
    unrealized_pnl_total: Decimal
    drawdown_pct: Decimal
    breached_stop_losses: list[str]
    marks: dict[str, Decimal]


@dataclass
class TradeResult:
    trade_id: str
    timestamp: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    realized_pnl: Decimal
    cash_after: Decimal
    position_qty_after: Decimal
    nav_after: Decimal
    applied_stop_loss: Decimal | None
