from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sim_trading.ds_operator import build_signal_entry_from_ds_decision, run_deepseek_shadow
from sim_trading.execution import SimulationExecutor
from sim_trading.ledger import LedgerService
from sim_trading.market import run_signal_snapshot
from sim_trading.models import ExecutionConfig, RiskConfig, ValidationConfig, decimal_to_str, now_iso, to_decimal
from sim_trading.storage import read_csv_rows, read_jsonl
from sim_trading.universe import resolve_universe_symbols

DEFAULT_STRATEGY_INITIAL_CAPITAL = Decimal("100")
DEFAULT_STRATEGY_LOOKBACK_POINTS = 6


@dataclass(frozen=True)
class StrategyProfile:
    name: str
    uses_ds: bool
    ds_bias: str | None
    universe_artifact: str
    daily_loss_cap_pct: Decimal
    description: str


STRATEGY_PROFILES: dict[str, StrategyProfile] = {
    "baseline": StrategyProfile(
        name="baseline",
        uses_ds=False,
        ds_bias=None,
        universe_artifact="top120",
        daily_loss_cap_pct=Decimal("0.03"),
        description="Rule-based baseline on the Top 120 universe. Daily loss breaker default: -3.0%.",
    ),
    "ds_conservative": StrategyProfile(
        name="ds_conservative",
        uses_ds=True,
        ds_bias="cautious",
        universe_artifact="top30",
        daily_loss_cap_pct=Decimal("0.025"),
        description="DeepSeek track with cautious bias on the Top 30 candidate set.",
    ),
    "ds_aggressive": StrategyProfile(
        name="ds_aggressive",
        uses_ds=True,
        ds_bias="normal",
        universe_artifact="top30",
        daily_loss_cap_pct=Decimal("0.04"),
        description="DeepSeek track with normal bias on the Top 30 candidate set.",
    ),
}


def resolve_strategy_profile(strategy: str) -> StrategyProfile:
    normalized = str(strategy).strip().lower()
    if normalized not in STRATEGY_PROFILES:
        raise ValueError(f"unsupported strategy '{strategy}'")
    return STRATEGY_PROFILES[normalized]


def strategy_state_dir(state_dir: Path | str, strategy: str) -> Path:
    root = LedgerService(state_dir).paths.strategies_root
    return root / resolve_strategy_profile(strategy).name


def load_strategy_selection(state_dir: Path | str) -> dict[str, Any]:
    service = LedgerService(state_dir)
    config = service.load_config_payload()
    strategy_control = config.get("strategy_control", {}) if isinstance(config, dict) else {}
    if not isinstance(strategy_control, dict):
        strategy_control = {}
    selected = str(strategy_control.get("selected_strategy", "")).strip().lower()
    enabled = bool(strategy_control.get("enabled", False)) and bool(selected)
    if selected and selected in STRATEGY_PROFILES:
        label = selected
    else:
        selected = ""
        enabled = False
        label = None
    return {
        "enabled": enabled,
        "selected_strategy": selected or None,
        "label": label,
    }


def set_strategy_selection(state_dir: Path | str, *, strategy: str | None, enabled: bool) -> dict[str, Any]:
    service = LedgerService(state_dir)
    config = service.load_config_payload()
    if not isinstance(config, dict):
        config = {}
    strategy_control = config.get("strategy_control", {})
    if not isinstance(strategy_control, dict):
        strategy_control = {}
    if strategy:
        profile = resolve_strategy_profile(strategy)
        strategy_control["selected_strategy"] = profile.name
    else:
        strategy_control["selected_strategy"] = ""
    strategy_control["enabled"] = bool(enabled and strategy_control.get("selected_strategy"))
    strategy_control["updated_at"] = now_iso()
    config["strategy_control"] = strategy_control
    service.save_config_payload(config)
    return load_strategy_selection(state_dir)


def build_strategy_signal_entry(
    state_dir: Path | str,
    *,
    strategy: str,
    timestamp: str | None = None,
    lookback_points: int = DEFAULT_STRATEGY_LOOKBACK_POINTS,
    source: str = "strategy.selection",
) -> dict[str, Any]:
    profile = resolve_strategy_profile(strategy)
    run_time = timestamp or now_iso()
    try:
        symbols = resolve_universe_symbols(state_dir, profile.universe_artifact)
    except Exception:  # noqa: BLE001
        root_config = LedgerService(state_dir).load_config_payload()
        strategy_payload = root_config.get("strategy", {}) if isinstance(root_config, dict) else {}
        configured_symbols = strategy_payload.get("symbols", []) if isinstance(strategy_payload, dict) else []
        symbols = [str(item) for item in configured_symbols if str(item).strip()]
        if not symbols:
            raise
    ensure_strategy_state(state_dir, strategy=profile.name, timestamp=run_time, symbols=symbols)
    strategy_dir = sync_shared_market_data(state_dir, strategy=profile.name)
    signal_entry = run_signal_snapshot(
        state_dir=strategy_dir,
        source=f"{source}.{profile.name}.signals",
        lookback_points=lookback_points,
        timestamp=run_time,
    ).entry
    if not profile.uses_ds:
        signal_entry["decision_source"] = profile.name
        signal_entry["summary"] = f"[{profile.name}] {signal_entry.get('summary', '')}".strip()
        return signal_entry

    ds_result = run_deepseek_shadow(
        state_dir=strategy_dir,
        source=f"{source}.{profile.name}.ds",
        timestamp=run_time,
        plan_bias=profile.ds_bias or "cautious",
    )
    if ds_result.decision_entry is None:
        signal_entry["decision_source"] = profile.name
        signal_entry["summary"] = f"[{profile.name}] DS unavailable, fallback signals: {signal_entry.get('summary', '')}".strip()
        return signal_entry

    ds_signal_entry = build_signal_entry_from_ds_decision(
        state_dir=strategy_dir,
        decision_entry=ds_result.decision_entry,
        source=f"{source}.{profile.name}.decision",
        timestamp=run_time,
    )
    ds_signal_entry["decision_source"] = profile.name
    ds_signal_entry["summary"] = f"[{profile.name}] {ds_signal_entry.get('summary', '')}".strip()
    return ds_signal_entry


def _shared_execution_config(state_dir: Path | str) -> ExecutionConfig:
    try:
        return LedgerService(state_dir).load_execution_config()
    except Exception:  # noqa: BLE001
        return ExecutionConfig.from_dict({})


def _shared_validation_config(state_dir: Path | str) -> ValidationConfig:
    try:
        return LedgerService(state_dir).load_validation_config()
    except Exception:  # noqa: BLE001
        return ValidationConfig.from_dict({}, default_initial_capital=DEFAULT_STRATEGY_INITIAL_CAPITAL)


def _strategy_risk_config(profile: StrategyProfile) -> RiskConfig:
    return RiskConfig(
        max_position_size_pct=Decimal("0.25"),
        daily_loss_cap_pct=profile.daily_loss_cap_pct,
        default_stop_loss_pct=Decimal("0.035"),
        max_gross_exposure_pct=Decimal("0.60"),
        max_concurrent_positions=10,
        require_stop_loss=True,
        consecutive_loss_limit=3,
        cooldown_cycles=3,
    )


def ensure_strategy_state(
    state_dir: Path | str,
    *,
    strategy: str,
    timestamp: str | None = None,
    symbols: list[str] | None = None,
) -> LedgerService:
    profile = resolve_strategy_profile(strategy)
    created_at = timestamp or now_iso()
    strategy_dir = strategy_state_dir(state_dir, profile.name)
    service = LedgerService(strategy_dir)
    if not service.paths.account.exists():
        execution_config = _shared_execution_config(state_dir)
        validation_config = _shared_validation_config(state_dir)
        seed_payload = {
            "account": {
                "account_id": f"sim-{profile.name}",
                "base_currency": "USDT",
                "cash_balance": decimal_to_str(DEFAULT_STRATEGY_INITIAL_CAPITAL),
                "created_at": created_at,
                "metadata": {"strategy_track": profile.name},
            },
            "positions": [],
            "risk": _strategy_risk_config(profile).to_dict(),
            "execution": execution_config.to_dict(),
            "validation": {
                **validation_config.to_dict(),
                "initial_capital": decimal_to_str(DEFAULT_STRATEGY_INITIAL_CAPITAL),
            },
            "strategy": {
                "name": "equal_weight_momentum",
                "track": profile.name,
                "uses_ds": profile.uses_ds,
                "ds_bias": profile.ds_bias,
                "symbols": symbols or [],
                "notes": profile.description,
            },
            "source_note": "strategy-track bootstrap seed",
            "source_path": str(Path(state_dir).resolve()),
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(json.dumps(seed_payload, indent=2, sort_keys=True) + "\n")
            seed_path = Path(handle.name)
        try:
            service.initialize_from_seed(seed_path)
        finally:
            seed_path.unlink(missing_ok=True)

    config_payload = service.load_config_payload()
    config_payload["risk"] = _strategy_risk_config(profile).to_dict()
    config_payload["execution"] = _shared_execution_config(state_dir).to_dict()
    config_payload["validation"] = {
        **_shared_validation_config(state_dir).to_dict(),
        "initial_capital": decimal_to_str(DEFAULT_STRATEGY_INITIAL_CAPITAL),
    }
    config_payload["strategy"] = {
        "name": "equal_weight_momentum",
        "track": profile.name,
        "uses_ds": profile.uses_ds,
        "ds_bias": profile.ds_bias,
        "symbols": symbols or config_payload.get("strategy", {}).get("symbols", []),
        "notes": profile.description,
    }
    service.save_config_payload(config_payload)
    return service


def sync_shared_market_data(state_dir: Path | str, *, strategy: str) -> Path:
    strategy_dir = strategy_state_dir(state_dir, strategy)
    strategy_paths = LedgerService(strategy_dir).paths
    root_paths = LedgerService(state_dir).paths
    for source_path, destination_path in (
        (root_paths.market_feed, strategy_paths.market_feed),
        (root_paths.market_prices, strategy_paths.market_prices),
    ):
        if source_path.exists():
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination_path)
    return strategy_dir


def run_strategy_track(
    state_dir: Path | str,
    *,
    strategy: str,
    timestamp: str | None = None,
    lookback_points: int = DEFAULT_STRATEGY_LOOKBACK_POINTS,
    source: str = "cli.strategy-run",
) -> dict[str, Any]:
    profile = resolve_strategy_profile(strategy)
    run_time = timestamp or now_iso()
    symbols = resolve_universe_symbols(state_dir, profile.universe_artifact)
    strategy_service = ensure_strategy_state(state_dir, strategy=profile.name, timestamp=run_time, symbols=symbols)
    strategy_dir = sync_shared_market_data(state_dir, strategy=profile.name)
    signal_entry = build_strategy_signal_entry(
        state_dir,
        strategy=profile.name,
        timestamp=run_time,
        lookback_points=lookback_points,
        source=source,
    )

    status = "ok"
    reason = str(signal_entry.get("summary", ""))
    decision_id = str(signal_entry.get("decision_id", "")).strip() or None
    execution_entry: dict[str, Any] | None = None

    execution_entry = SimulationExecutor(strategy_dir).execute_cycle(
        timestamp=run_time,
        signal_run_entry=signal_entry,
        source=f"{source}.{profile.name}",
        lookback_points=lookback_points,
    ).entry
    snapshot = strategy_service.build_snapshot(timestamp=run_time)
    return {
        "strategy": profile.name,
        "state_dir": str(strategy_dir),
        "status": status,
        "reason": reason,
        "signal_summary": signal_entry.get("summary"),
        "decision_id": decision_id,
        "nav": decimal_to_str(snapshot.nav),
        "execution": execution_entry,
    }


def _risk_trigger_count(state_dir: Path | str) -> int:
    count = 0
    for row in read_jsonl(LedgerService(state_dir).paths.risk_events):
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "")).lower() in {"blocked", "rejected"}:
            count += 1
    return count


def _profit_factor(closed_rows: list[dict[str, str]]) -> str:
    winners = [to_decimal(row["realized_pnl"]) for row in closed_rows if to_decimal(row["realized_pnl"]) > 0]
    losers = [to_decimal(row["realized_pnl"]) for row in closed_rows if to_decimal(row["realized_pnl"]) < 0]
    gross_profit = sum(winners, Decimal("0"))
    gross_loss_abs = abs(sum(losers, Decimal("0")))
    if gross_loss_abs == 0:
        return "inf" if gross_profit > 0 else "0"
    return decimal_to_str(gross_profit / gross_loss_abs)


def build_strategy_comparison(
    state_dir: Path | str,
    *,
    timestamp: str | None = None,
    ensure_initialized: bool = False,
) -> dict[str, Any]:
    generated_at = timestamp or now_iso()
    entries: list[dict[str, Any]] = []
    for profile in STRATEGY_PROFILES.values():
        if ensure_initialized:
            try:
                symbols = resolve_universe_symbols(state_dir, profile.universe_artifact)
            except Exception:  # noqa: BLE001
                symbols = []
            ensure_strategy_state(state_dir, strategy=profile.name, timestamp=generated_at, symbols=symbols)
        strategy_dir = strategy_state_dir(state_dir, profile.name)
        if not (strategy_dir / "account.json").exists():
            entries.append(
                {
                    "strategy": profile.name,
                    "initialized": False,
                    "state_dir": str(strategy_dir),
                    "uses_ds": profile.uses_ds,
                    "ds_bias": profile.ds_bias,
                    "daily_loss_breaker_pct": decimal_to_str(-profile.daily_loss_cap_pct),
                    "return_pct": None,
                    "max_drawdown_pct": None,
                    "win_rate": None,
                    "profit_factor": None,
                    "turnover_ratio": None,
                    "risk_trigger_count": 0,
                    "nav": None,
                    "position_count": 0,
                }
            )
            continue

        service = LedgerService(strategy_dir)
        snapshot = service.build_snapshot(timestamp=generated_at)
        equity_rows = read_csv_rows(service.paths.equity_curve)
        trade_rows = read_csv_rows(service.paths.trades)
        starting_nav = to_decimal(equity_rows[0]["nav"]) if equity_rows else DEFAULT_STRATEGY_INITIAL_CAPITAL
        ending_nav = to_decimal(equity_rows[-1]["nav"]) if equity_rows else snapshot.nav
        closed_rows = [row for row in trade_rows if to_decimal(row["realized_pnl"]) != 0]
        winners = [row for row in closed_rows if to_decimal(row["realized_pnl"]) > 0]
        return_pct = (ending_nav / starting_nav) - Decimal("1") if starting_nav > 0 else Decimal("0")
        max_drawdown_pct = min((to_decimal(row["drawdown_pct"]) for row in equity_rows), default=Decimal("0"))
        win_rate = (Decimal(len(winners)) / Decimal(len(closed_rows))) if closed_rows else Decimal("0")
        turnover_ratio = (
            sum((abs(to_decimal(row["notional"])) for row in trade_rows), Decimal("0")) / starting_nav
            if starting_nav > 0
            else Decimal("0")
        )
        entries.append(
            {
                "strategy": profile.name,
                "initialized": True,
                "state_dir": str(strategy_dir),
                "uses_ds": profile.uses_ds,
                "ds_bias": profile.ds_bias,
                "daily_loss_breaker_pct": decimal_to_str(-profile.daily_loss_cap_pct),
                "return_pct": decimal_to_str(return_pct),
                "max_drawdown_pct": decimal_to_str(max_drawdown_pct),
                "win_rate": decimal_to_str(win_rate),
                "profit_factor": _profit_factor(closed_rows),
                "turnover_ratio": decimal_to_str(turnover_ratio),
                "risk_trigger_count": _risk_trigger_count(strategy_dir),
                "nav": decimal_to_str(snapshot.nav),
                "position_count": len(service.load_positions()),
            }
        )
    recommended = _recommend_strategy_weights(entries)
    return {
        "generated_at": generated_at,
        "strategies": entries,
        "recommended_allocation": recommended,
    }


def _score_strategy_row(row: dict[str, Any]) -> Decimal:
    if not bool(row.get("initialized")):
        return Decimal("-999")
    return_pct = to_decimal(row.get("return_pct", "0"))
    max_drawdown = abs(to_decimal(row.get("max_drawdown_pct", "0")))
    win_rate = to_decimal(row.get("win_rate", "0"))
    turnover = to_decimal(row.get("turnover_ratio", "0"))
    risk_triggers = Decimal(int(row.get("risk_trigger_count", 0) or 0))
    score = (
        (return_pct * Decimal("1.0"))
        - (max_drawdown * Decimal("0.7"))
        + (win_rate * Decimal("0.25"))
        - (turnover * Decimal("0.10"))
        - (risk_triggers * Decimal("0.02"))
    )
    return score


def _recommend_strategy_weights(rows: list[dict[str, Any]]) -> dict[str, Any]:
    initialized = [row for row in rows if isinstance(row, dict) and row.get("initialized")]
    if not initialized:
        return {
            "status": "watch",
            "summary": "No initialized strategy tracks are available for allocation guidance.",
            "lead_strategy": None,
            "lead_score": None,
            "weights": [],
        }

    scored_rows = []
    for row in initialized:
        score = _score_strategy_row(row)
        scored_rows.append((row, max(score, Decimal("0"))))

    score_sum = sum((score for _, score in scored_rows), Decimal("0"))
    if score_sum <= 0:
        even = Decimal("1") / Decimal(len(scored_rows))
        weighted = [(row, even) for row, _ in scored_rows]
    else:
        weighted = [(row, score / score_sum) for row, score in scored_rows]

    weighted.sort(key=lambda item: item[1], reverse=True)
    lead_row, lead_weight = weighted[0]
    lead_score = _score_strategy_row(lead_row)
    status = "ok" if lead_weight >= Decimal("0.45") else "watch"

    return {
        "status": status,
        "summary": (
            f"Suggested lead strategy is {lead_row.get('strategy')} "
            + f"with allocation weight {decimal_to_str(lead_weight)} based on return/drawdown/win-rate/turnover/risk-trigger scoring."
        ),
        "lead_strategy": lead_row.get("strategy"),
        "lead_score": decimal_to_str(lead_score),
        "weights": [
            {
                "strategy": row.get("strategy"),
                "weight": decimal_to_str(weight),
                "score": decimal_to_str(_score_strategy_row(row)),
                "return_pct": row.get("return_pct"),
                "max_drawdown_pct": row.get("max_drawdown_pct"),
                "win_rate": row.get("win_rate"),
                "turnover_ratio": row.get("turnover_ratio"),
                "risk_trigger_count": row.get("risk_trigger_count", 0),
            }
            for row, weight in weighted
        ],
    }


def format_strategy_compare_table(compare_payload: dict[str, Any]) -> str:
    headers = [
        ("strategy", 18),
        ("return", 10),
        ("max_dd", 10),
        ("win_rate", 10),
        ("profit_factor", 14),
        ("turnover", 10),
        ("risk", 6),
        ("rec_w", 8),
        ("nav", 10),
    ]
    lines = [
        " ".join(label.ljust(width) for label, width in headers),
        " ".join(("-" * len(label)).ljust(width) for label, width in headers),
    ]
    recommendation = compare_payload.get("recommended_allocation", {})
    recommended_weights = {
        str(item.get("strategy")): to_decimal(item.get("weight", "0"))
        for item in recommendation.get("weights", [])
        if isinstance(item, dict) and item.get("strategy")
    }
    for row in compare_payload.get("strategies", []):
        if not isinstance(row, dict):
            continue
        values = [
            str(row.get("strategy", "n/a")),
            "n/a" if row.get("return_pct") is None else f"{to_decimal(row['return_pct']):.2%}",
            "n/a" if row.get("max_drawdown_pct") is None else f"{to_decimal(row['max_drawdown_pct']):.2%}",
            "n/a" if row.get("win_rate") is None else f"{to_decimal(row['win_rate']):.2%}",
            str(row.get("profit_factor", "n/a")),
            "n/a" if row.get("turnover_ratio") is None else f"{to_decimal(row['turnover_ratio']):.2%}",
            str(row.get("risk_trigger_count", 0)),
            "n/a" if row.get("strategy") not in recommended_weights else f"{recommended_weights[str(row['strategy'])]:.2%}",
            "n/a" if row.get("nav") is None else f"{to_decimal(row['nav']):.2f}",
        ]
        lines.append(" ".join(value.ljust(width) for value, (_, width) in zip(values, headers)))
    return "\n".join(lines)
