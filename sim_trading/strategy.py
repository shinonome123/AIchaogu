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


class MeanReversionStrategy(Strategy):
    """Buys symbols with negative momentum that show EMA stabilization and equal-weights them."""

    name = "mean_reversion"

    def __init__(self, min_drawdown_momentum: Decimal = Decimal("-0.08")) -> None:
        self.min_drawdown_momentum = min_drawdown_momentum

    def generate_targets(
        self,
        *,
        nav: Decimal,
        signals: Iterable[MarketSignal],
        risk_config: RiskConfig,
    ) -> list[TargetAllocation]:
        if nav <= 0:
            return []
        candidates = [
            signal
            for signal in signals
            if self.min_drawdown_momentum <= signal.momentum_7d < Decimal("0") and signal.ema_slope >= Decimal("0")
        ]
        if not candidates:
            return []
        candidates.sort(key=lambda signal: (signal.momentum_7d, signal.ema_slope, signal.symbol))
        selected = candidates[: max(1, risk_config.max_concurrent_positions)]
        gross_target = min(Decimal("1"), risk_config.max_gross_exposure_pct)
        equal_weight = gross_target / Decimal(len(selected))
        capped_weight = min(equal_weight, risk_config.max_position_size_pct)
        if capped_weight <= 0:
            return []
        return [
            TargetAllocation(
                symbol=signal.symbol,
                target_weight=capped_weight,
                rationale=(
                    f"7d momentum {signal.momentum_7d} indicates pullback while EMA slope {signal.ema_slope} stabilized; "
                    + f"mean-reversion weight capped by gross {risk_config.max_gross_exposure_pct} and per-symbol {risk_config.max_position_size_pct}"
                ),
            )
            for signal in selected
        ]


class BreakoutMomentumStrategy(Strategy):
    """Focuses on stronger momentum breakouts and concentrates to top-confidence symbols."""

    name = "breakout_momentum"

    def __init__(self, min_momentum: Decimal = Decimal("0.02"), max_positions: int = 5) -> None:
        self.min_momentum = min_momentum
        self.max_positions = max(1, max_positions)

    def generate_targets(
        self,
        *,
        nav: Decimal,
        signals: Iterable[MarketSignal],
        risk_config: RiskConfig,
    ) -> list[TargetAllocation]:
        if nav <= 0:
            return []
        candidates = [
            signal
            for signal in signals
            if signal.momentum_7d >= self.min_momentum and signal.ema_slope > Decimal("0")
        ]
        if not candidates:
            return []
        candidates.sort(
            key=lambda signal: (signal.momentum_7d, signal.ema_slope, signal.confidence, signal.symbol),
            reverse=True,
        )
        selected = candidates[: min(self.max_positions, max(1, risk_config.max_concurrent_positions))]
        gross_target = min(Decimal("1"), risk_config.max_gross_exposure_pct)
        equal_weight = gross_target / Decimal(len(selected))
        capped_weight = min(equal_weight, risk_config.max_position_size_pct)
        if capped_weight <= 0:
            return []
        return [
            TargetAllocation(
                symbol=signal.symbol,
                target_weight=capped_weight,
                rationale=(
                    f"Breakout momentum {signal.momentum_7d} and EMA slope {signal.ema_slope} passed threshold {self.min_momentum}; "
                    + f"target capped by gross {risk_config.max_gross_exposure_pct} and per-symbol {risk_config.max_position_size_pct}"
                ),
            )
            for signal in selected
        ]


class TieredMomentumStrategy(Strategy):
    """Ranks momentum leaders and allocates with a tiered rank-decay weighting."""

    name = "tiered_momentum"

    def __init__(self, min_momentum: Decimal = Decimal("0.01"), max_positions: int = 5) -> None:
        self.min_momentum = min_momentum
        self.max_positions = max(1, max_positions)

    def generate_targets(
        self,
        *,
        nav: Decimal,
        signals: Iterable[MarketSignal],
        risk_config: RiskConfig,
    ) -> list[TargetAllocation]:
        if nav <= 0:
            return []
        candidates = [
            signal
            for signal in signals
            if signal.momentum_7d >= self.min_momentum and signal.ema_slope > Decimal("0")
        ]
        if not candidates:
            return []
        candidates.sort(
            key=lambda signal: (signal.momentum_7d, signal.ema_slope, signal.confidence, signal.symbol),
            reverse=True,
        )
        limit = min(self.max_positions, max(1, risk_config.max_concurrent_positions))
        selected = candidates[:limit]
        gross_target = min(Decimal("1"), risk_config.max_gross_exposure_pct)
        if gross_target <= 0:
            return []

        tier_scores = [Decimal(limit - idx) for idx in range(limit)]
        score_sum = sum(tier_scores)
        if score_sum <= 0:
            return []

        allocations: list[TargetAllocation] = []
        for idx, signal in enumerate(selected):
            raw_weight = gross_target * (tier_scores[idx] / score_sum)
            target_weight = min(raw_weight, risk_config.max_position_size_pct)
            if target_weight <= 0:
                continue
            allocations.append(
                TargetAllocation(
                    symbol=signal.symbol,
                    target_weight=target_weight,
                    rationale=(
                        f"Tiered momentum rank {idx + 1}/{limit}: momentum {signal.momentum_7d}, "
                        + f"EMA slope {signal.ema_slope}, confidence {signal.confidence}; "
                        + f"weight from rank-decay schedule capped at {risk_config.max_position_size_pct}"
                    ),
                )
            )
        return allocations
