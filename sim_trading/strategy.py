from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sim_trading.models import RiskConfig


@dataclass(frozen=True)
class MarketSignal:
    symbol: str
    momentum_7d: Decimal
    ema_slope: Decimal
    confidence: Decimal = Decimal("1")


@dataclass(frozen=True)
class TargetAllocation:
    symbol: str
    target_weight: Decimal
    rationale: str


class Strategy(ABC):
    name: str

    @abstractmethod
    def generate_targets(
        self,
        *,
        nav: Decimal,
        signals: Iterable[MarketSignal],
        risk_config: RiskConfig,
    ) -> list[TargetAllocation]:
        raise NotImplementedError


class EqualWeightMomentumStrategy(Strategy):
    """A simple example strategy that equal-weights symbols with positive momentum and EMA slope."""

    name = "equal_weight_momentum"

    def __init__(self, min_momentum: Decimal = Decimal("0")) -> None:
        self.min_momentum = min_momentum

    def generate_targets(
        self,
        *,
        nav: Decimal,
        signals: Iterable[MarketSignal],
        risk_config: RiskConfig,
    ) -> list[TargetAllocation]:
        qualified = [
            signal
            for signal in signals
            if signal.momentum_7d > self.min_momentum and signal.ema_slope > Decimal("0")
        ]
        if not qualified or nav <= 0:
            return []

        qualified.sort(
            key=lambda signal: (
                signal.momentum_7d,
                signal.ema_slope,
                signal.confidence,
                signal.symbol,
            ),
            reverse=True,
        )
        selected = qualified[: max(1, risk_config.max_concurrent_positions)]
        if not selected:
            return []

        gross_target = min(Decimal("1"), risk_config.max_gross_exposure_pct)
        equal_weight = gross_target / Decimal(len(selected))
        capped_weight = min(equal_weight, risk_config.max_position_size_pct)
        if capped_weight <= 0:
            return []
        allocations: list[TargetAllocation] = []
        for signal in selected:
            allocations.append(
                TargetAllocation(
                    symbol=signal.symbol,
                    target_weight=capped_weight,
                    rationale=(
                        f"7d momentum {signal.momentum_7d} and EMA slope {signal.ema_slope} "
                        + f"passed filters at confidence {signal.confidence}; "
                        + f"target capped by gross {risk_config.max_gross_exposure_pct} and per-symbol {risk_config.max_position_size_pct}"
                    ),
                )
            )
        return allocations
