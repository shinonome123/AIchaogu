from __future__ import annotations

from decimal import Decimal

from sim_trading.models import Position, RiskConfig, quantize_8


class RiskViolation(ValueError):
    """Raised when a simulated trade breaks configured risk limits."""


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def resolve_stop_loss(self, side: str, price: Decimal, provided_stop_loss: Decimal | None) -> Decimal | None:
        if side == "sell":
            return None
        if provided_stop_loss is not None:
            return quantize_8(provided_stop_loss)
        if not self.config.require_stop_loss:
            return None
        return quantize_8(price * (Decimal("1") - self.config.default_stop_loss_pct))

    def validate_trade(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        cash_balance: Decimal,
        fee: Decimal,
        current_position: Position | None,
        nav: Decimal,
        day_open_nav: Decimal,
        stop_loss: Decimal | None,
        positions: dict[str, Position] | None = None,
        marks: dict[str, Decimal] | None = None,
    ) -> None:
        violations: list[str] = []
        notional = quantity * price

        if side == "buy" and cash_balance < notional + fee:
            violations.append("insufficient cash for requested buy notional")

        if side == "buy":
            existing_notional = (current_position.quantity * price) if current_position else Decimal("0")
            resulting_notional = existing_notional + notional
            if nav > 0 and resulting_notional > nav * self.config.max_position_size_pct:
                violations.append(
                    f"position {symbol} exceeds max position size of {self.config.max_position_size_pct:.0%} NAV"
                )
            if positions:
                gross_exposure = Decimal("0")
                concurrent_positions = 0
                for current_symbol, position in positions.items():
                    mark = (marks or {}).get(current_symbol, position.last_price)
                    if current_symbol == symbol:
                        if current_position is not None:
                            gross_exposure += resulting_notional
                            if current_position.quantity + quantity > 0:
                                concurrent_positions += 1
                        else:
                            gross_exposure += resulting_notional
                            if quantity > 0:
                                concurrent_positions += 1
                        continue
                    if position.quantity > 0:
                        gross_exposure += position.quantity * mark
                        concurrent_positions += 1
                if current_position is None and symbol not in positions and quantity > 0:
                    gross_exposure += resulting_notional
                    concurrent_positions += 1
                if nav > 0 and gross_exposure > nav * self.config.max_gross_exposure_pct:
                    violations.append(
                        f"gross exposure exceeds max gross exposure of {self.config.max_gross_exposure_pct:.0%} NAV"
                    )
                if concurrent_positions > self.config.max_concurrent_positions:
                    violations.append(
                        f"concurrent positions exceed max of {self.config.max_concurrent_positions}"
                    )

        if side == "sell":
            if current_position is None or current_position.quantity < quantity:
                violations.append(f"cannot sell {quantity} {symbol} without an existing long position")

        if side == "buy" and day_open_nav > 0 and nav <= day_open_nav * (Decimal("1") - self.config.daily_loss_cap_pct):
            violations.append(
                f"daily loss cap hit: NAV {nav} is below {self.config.daily_loss_cap_pct:.0%} loss threshold"
            )

        if stop_loss is not None and side == "buy" and stop_loss >= price:
            violations.append("stop-loss must be below the buy price for long positions")

        if violations:
            raise RiskViolation("; ".join(violations))

    def breached_stop_losses(
        self,
        positions: dict[str, Position],
        marks: dict[str, Decimal],
    ) -> list[str]:
        breached: list[str] = []
        for symbol, position in positions.items():
            if position.stop_loss is None:
                continue
            mark = marks.get(symbol, position.last_price)
            if mark <= position.stop_loss:
                breached.append(symbol)
        return breached
