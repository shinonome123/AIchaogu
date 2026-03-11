from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from sim_trading.execution import build_risk_status
from sim_trading.ledger import LedgerService
from sim_trading.market import load_latest_market_fetch, load_latest_signal_run, resolve_market_symbols
from sim_trading.models import decimal_to_str, normalize_symbol, now_iso, quantize_8, to_decimal
from sim_trading.storage import append_jsonl, read_jsonl, read_last_jsonl

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RETRIES = 2

DEEPSEEK_API_KEY_ENV = "SIM_TRADING_DEEPSEEK_API_KEY"
DEEPSEEK_BASE_URL_ENV = "SIM_TRADING_DEEPSEEK_BASE_URL"
DEEPSEEK_MODEL_ENV = "SIM_TRADING_DEEPSEEK_MODEL"
DEEPSEEK_ENABLED_ENV = "SIM_TRADING_DEEPSEEK_ENABLED"
DEEPSEEK_TIMEOUT_ENV = "SIM_TRADING_DEEPSEEK_TIMEOUT_SECONDS"
DEEPSEEK_MAX_RETRIES_ENV = "SIM_TRADING_DEEPSEEK_MAX_RETRIES"

MARKET_REGIMES = {"trending", "ranging", "risk_off"}
GLOBAL_RISK_MODES = {"normal", "cautious", "defensive"}
DECISION_ACTIONS = {"buy", "sell", "hold"}

MARKET_REGIME_ALIASES = {
    "bullish": "trending",
    "bearish": "risk_off",
    "sideways": "ranging",
    "neutral": "ranging",
    "uncertain": "ranging",
    "mixed": "ranging",
    "choppy": "ranging",
    "volatile": "risk_off",
    "risk-off": "risk_off",
    "risk_off": "risk_off",
    "riskoff": "risk_off",
    "risk-on": "trending",
    "risk_on": "trending",
    "riskon": "trending",
}

GLOBAL_RISK_MODE_ALIASES = {
    "conservative": "cautious",
    "conservative_cooldown": "cautious",
    "cautious_cooldown": "cautious",
    "aggressive": "normal",
    "balanced": "normal",
    "neutral": "normal",
    "risk-off": "defensive",
    "risk_off": "defensive",
    "riskoff": "defensive",
    "defense": "defensive",
    "defence": "defensive",
    "defensive_cooldown": "defensive",
}

ACTION_ALIASES = {
    "long": "buy",
    "short": "sell",
    "flat": "hold",
    "wait": "hold",
    "no_trade": "hold",
}


class DeepSeekDecisionError(ValueError):
    """Raised when a DeepSeek response cannot be validated or converted."""


@dataclass(frozen=True)
class DeepSeekConfig:
    enabled: bool
    api_key: str | None
    base_url: str
    model: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    disabled_reason: str | None = None

    @property
    def chat_completions_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"


@dataclass(frozen=True)
class DeepSeekShadowRunResult:
    status: str
    reason: str
    request_entry: dict[str, Any]
    decision_entry: dict[str, Any] | None = None
    rejection_entry: dict[str, Any] | None = None


def _env_enabled(raw_value: str | None) -> bool:
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(raw_value: str | None, *, default: int, minimum: int = 0, maximum: int = 600) -> int:
    if raw_value is None or not str(raw_value).strip():
        return default
    try:
        value = int(str(raw_value).strip())
    except ValueError:
        return default
    if value < minimum:
        value = minimum
    if value > maximum:
        value = maximum
    return value


def _normalize_enum(raw_value: Any, *, allowed: set[str], aliases: dict[str, str], field_name: str) -> str:
    value = str(raw_value or "").strip().lower()
    value = aliases.get(value, value)

    if value not in allowed:
        compact = re.sub(r"[^a-z]+", "_", value).strip("_")
        if compact:
            value = aliases.get(compact, value)

    if value not in allowed:
        # Heuristic fallback for composite labels like "neutral_to_bearish"
        compact = re.sub(r"[^a-z]+", "_", str(raw_value or "").strip().lower()).strip("_")
        if field_name == "market_regime":
            if "bear" in compact or "risk_off" in compact or "riskoff" in compact:
                value = "risk_off"
            elif "bull" in compact or "trend" in compact or "risk_on" in compact or "riskon" in compact:
                value = "trending"
            elif "neutral" in compact or "range" in compact or "side" in compact:
                value = "ranging"
        elif field_name == "global_risk_mode":
            if "defens" in compact or "risk_off" in compact or "riskoff" in compact:
                value = "defensive"
            elif "conserv" in compact or "cauti" in compact:
                value = "cautious"
            elif "normal" in compact or "balanced" in compact or "neutral" in compact or "aggres" in compact:
                value = "normal"

    if value not in allowed:
        raise DeepSeekDecisionError(f"{field_name} must be one of {'|'.join(sorted(allowed))}")
    return value


def load_deepseek_config() -> DeepSeekConfig:
    enabled = _env_enabled(os.getenv(DEEPSEEK_ENABLED_ENV))
    api_key = os.getenv(DEEPSEEK_API_KEY_ENV, "").strip() or None
    base_url = os.getenv(DEEPSEEK_BASE_URL_ENV, "").strip() or DEFAULT_DEEPSEEK_BASE_URL
    model = os.getenv(DEEPSEEK_MODEL_ENV, "").strip() or DEFAULT_DEEPSEEK_MODEL
    timeout_seconds = _env_int(
        os.getenv(DEEPSEEK_TIMEOUT_ENV),
        default=DEFAULT_TIMEOUT_SECONDS,
        minimum=5,
        maximum=120,
    )
    max_retries = _env_int(
        os.getenv(DEEPSEEK_MAX_RETRIES_ENV),
        default=DEFAULT_MAX_RETRIES,
        minimum=0,
        maximum=8,
    )

    disabled_reason: str | None = None
    if not enabled:
        disabled_reason = f"{DEEPSEEK_ENABLED_ENV}=0"
    elif api_key is None:
        disabled_reason = f"{DEEPSEEK_API_KEY_ENV} is not configured"

    return DeepSeekConfig(
        enabled=enabled and api_key is not None,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        disabled_reason=disabled_reason,
    )


def _request_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12].upper()}"


def _summary_from_payload(payload: dict[str, Any]) -> str:
    decisions = payload.get("decisions", [])
    if not isinstance(decisions, list):
        decisions = []
    buy_count = len([item for item in decisions if isinstance(item, dict) and item.get("action") == "buy"])
    sell_count = len([item for item in decisions if isinstance(item, dict) and item.get("action") == "sell"])
    hold_count = len([item for item in decisions if isinstance(item, dict) and item.get("action") == "hold"])
    return (
        f"regime={payload.get('market_regime', 'unknown')} "
        + f"risk={payload.get('global_risk_mode', 'unknown')} "
        + f"buy={buy_count} sell={sell_count} hold={hold_count}"
    )


def _extract_json_text(content: str) -> str:
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        return content[start : end + 1].strip()
    return content.strip()


def _extract_message_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DeepSeekDecisionError("DeepSeek API response did not include choices")
    message = choices[0].get("message", {})
    if not isinstance(message, dict):
        raise DeepSeekDecisionError("DeepSeek API response message was malformed")
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts)
    raise DeepSeekDecisionError("DeepSeek API response content was empty")


def _normalized_fraction(value: Any, *, field_name: str) -> str:
    try:
        numeric = quantize_8(to_decimal(value))
    except Exception as exc:  # noqa: BLE001
        raise DeepSeekDecisionError(f"{field_name} must be numeric") from exc
    if numeric < 0 or numeric > 1:
        raise DeepSeekDecisionError(f"{field_name} must be between 0 and 1")
    return decimal_to_str(numeric)


def validate_deepseek_payload(
    payload: Any,
    *,
    known_symbols: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DeepSeekDecisionError("DeepSeek payload must be a JSON object")

    allowed_root_keys = {"market_regime", "global_risk_mode", "decisions", "no_trade_reason"}
    extra_root_keys = set(payload) - allowed_root_keys
    if extra_root_keys:
        raise DeepSeekDecisionError(f"unexpected top-level keys: {', '.join(sorted(extra_root_keys))}")

    market_regime = _normalize_enum(
        payload.get("market_regime", ""),
        allowed=MARKET_REGIMES,
        aliases=MARKET_REGIME_ALIASES,
        field_name="market_regime",
    )

    global_risk_mode = _normalize_enum(
        payload.get("global_risk_mode", ""),
        allowed=GLOBAL_RISK_MODES,
        aliases=GLOBAL_RISK_MODE_ALIASES,
        field_name="global_risk_mode",
    )

    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise DeepSeekDecisionError("decisions must be a JSON array")

    normalized_decisions: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    required_decision_keys = {
        "symbol",
        "action",
        "target_weight",
        "confidence",
        "entry_reason",
        "invalidation",
        "stop_loss_pct",
        "take_profit_pct",
    }
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            raise DeepSeekDecisionError(f"decisions[{index}] must be a JSON object")
        extra_decision_keys = set(decision) - required_decision_keys
        missing_decision_keys = required_decision_keys - set(decision)
        if extra_decision_keys:
            raise DeepSeekDecisionError(
                f"decisions[{index}] included unexpected keys: {', '.join(sorted(extra_decision_keys))}"
            )
        if missing_decision_keys:
            raise DeepSeekDecisionError(
                f"decisions[{index}] is missing keys: {', '.join(sorted(missing_decision_keys))}"
            )

        symbol = normalize_symbol(str(decision["symbol"]))
        if not symbol:
            raise DeepSeekDecisionError(f"decisions[{index}].symbol must be non-empty")
        if symbol in seen_symbols:
            raise DeepSeekDecisionError(f"duplicate decision symbol: {symbol}")
        if known_symbols is not None and symbol not in known_symbols:
            raise DeepSeekDecisionError(f"decision symbol is outside current market universe: {symbol}")
        seen_symbols.add(symbol)

        action = str(decision["action"]).strip().lower()
        action = ACTION_ALIASES.get(action, action)
        if action not in DECISION_ACTIONS:
            raise DeepSeekDecisionError(f"decisions[{index}].action must be one of buy|sell|hold")

        entry_reason = str(decision["entry_reason"]).strip()
        invalidation = str(decision["invalidation"]).strip()
        if not entry_reason:
            raise DeepSeekDecisionError(f"decisions[{index}].entry_reason must be non-empty")
        if not invalidation:
            raise DeepSeekDecisionError(f"decisions[{index}].invalidation must be non-empty")

        normalized_decisions.append(
            {
                "symbol": symbol,
                "action": action,
                "target_weight": _normalized_fraction(decision["target_weight"], field_name="target_weight"),
                "confidence": _normalized_fraction(decision["confidence"], field_name="confidence"),
                "entry_reason": entry_reason,
                "invalidation": invalidation,
                "stop_loss_pct": _normalized_fraction(decision["stop_loss_pct"], field_name="stop_loss_pct"),
                "take_profit_pct": _normalized_fraction(
                    decision["take_profit_pct"],
                    field_name="take_profit_pct",
                ),
            }
        )

    no_trade_reason = None
    if "no_trade_reason" in payload:
        if payload["no_trade_reason"] is None:
            no_trade_reason = None
        else:
            no_trade_reason = str(payload["no_trade_reason"]).strip()
            if not no_trade_reason:
                raise DeepSeekDecisionError("no_trade_reason must be non-empty when provided")

    if not normalized_decisions and not no_trade_reason:
        raise DeepSeekDecisionError("either decisions or no_trade_reason must be present")

    normalized_payload: dict[str, Any] = {
        "market_regime": market_regime,
        "global_risk_mode": global_risk_mode,
        "decisions": normalized_decisions,
    }
    if no_trade_reason:
        normalized_payload["no_trade_reason"] = no_trade_reason
    return normalized_payload


def _position_rows_for_context(service: LedgerService, *, timestamp: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    snapshot = service.build_snapshot(timestamp=timestamp)
    rows: list[dict[str, Any]] = []
    current_weights: dict[str, str] = {}
    positions = service.load_positions()
    for symbol in sorted(positions):
        position = positions[symbol]
        mark = snapshot.marks.get(symbol, position.last_price)
        market_value = position.market_value(mark)
        current_weight = (
            decimal_to_str(quantize_8(market_value / snapshot.nav))
            if snapshot.nav > 0
            else "0"
        )
        current_weights[symbol] = current_weight
        rows.append(
            {
                "symbol": symbol,
                "quantity": decimal_to_str(position.quantity),
                "average_entry_price": decimal_to_str(position.average_entry_price),
                "mark_price": decimal_to_str(mark),
                "market_value": decimal_to_str(market_value),
                "current_weight": current_weight,
                "stop_loss": decimal_to_str(position.stop_loss) if position.stop_loss is not None else None,
            }
        )
    return rows, current_weights


def build_deepseek_context(
    state_dir: Path | str,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    run_time = timestamp or now_iso()
    service = LedgerService(state_dir)
    latest_market_fetch = load_latest_market_fetch(state_dir)
    latest_signal_run = load_latest_signal_run(state_dir)
    if latest_market_fetch is None:
        raise FileNotFoundError("no market feed snapshot available; run fetch-market first")
    if latest_signal_run is None:
        raise FileNotFoundError("no signal snapshot available; run run-signals first")

    tracked_symbols = set()
    tracked_symbols.update(str(item) for item in latest_signal_run.get("symbols", []) if str(item).strip())
    prices = latest_market_fetch.get("prices", {})
    if isinstance(prices, dict):
        tracked_symbols.update(str(symbol) for symbol in prices)
    try:
        tracked_symbols.update(resolve_market_symbols(state_dir))
    except Exception:  # noqa: BLE001
        pass

    positions, current_weights = _position_rows_for_context(service, timestamp=run_time)
    tracked_symbols.update(item["symbol"] for item in positions)
    snapshot = service.build_snapshot(timestamp=run_time)
    risk_status = build_risk_status(
        state_dir,
        snapshot={"timestamp": snapshot.timestamp, "nav": decimal_to_str(snapshot.nav)},
    )
    return {
        "timestamp": run_time,
        "portfolio": {
            "nav": decimal_to_str(snapshot.nav),
            "cash_balance": decimal_to_str(snapshot.cash_balance),
            "positions_market_value": decimal_to_str(snapshot.positions_market_value),
            "drawdown_pct": decimal_to_str(snapshot.drawdown_pct),
            "current_weights": current_weights,
            "positions": positions,
        },
        "market": latest_market_fetch,
        "signals": latest_signal_run,
        "risk_status": risk_status,
        "risk_config": service.load_risk_config().to_dict(),
        "tracked_symbols": sorted(normalize_symbol(symbol) for symbol in tracked_symbols if str(symbol).strip()),
    }


def _build_messages(context: dict[str, Any], *, plan_bias: str) -> list[dict[str, str]]:
    bias_text = "conservative" if plan_bias == "cautious" else "balanced"
    system_prompt = (
        "You are a simulation-only trading operator. "
        "Return JSON only with keys market_regime, global_risk_mode, decisions, and optional no_trade_reason. "
        "Use only buy, sell, or hold actions. Use long-only target_weight values between 0 and 1. "
        "Do not suggest leverage, shorting, or external execution. "
        "Prefer hold when evidence is weak. "
        "Each decision must include symbol, action, target_weight, confidence, entry_reason, invalidation, "
        "stop_loss_pct, and take_profit_pct."
    )
    user_prompt = (
        f"Build a {bias_text} operator plan for the next simulation cycle using this context:\n"
        + json.dumps(context, ensure_ascii=True, sort_keys=True)
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


class DeepSeekClient:
    def __init__(self, config: DeepSeekConfig) -> None:
        self.config = config

    def create_plan(self, *, context: dict[str, Any], plan_bias: str = "cautious") -> dict[str, Any]:
        if not self.config.enabled or self.config.api_key is None:
            raise DeepSeekDecisionError(self.config.disabled_reason or "DeepSeek client is disabled")

        body = {
            "model": self.config.model,
            "temperature": 0.1,
            "stream": False,
            "messages": _build_messages(context, plan_bias=plan_bias),
        }
        rendered_body = json.dumps(body).encode("utf-8")
        request = Request(
            self.config.chat_completions_url,
            method="POST",
            data=rendered_body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "sim-trading/0.3",
            },
        )

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                message_text = _extract_message_text(payload)
                return {
                    "response_id": str(payload.get("id", "")).strip() or None,
                    "raw_response": payload,
                    "content": message_text,
                    "parsed_json": json.loads(_extract_json_text(message_text)),
                }
            except HTTPError as exc:
                last_error = exc
                should_retry = exc.code in {408, 409, 429, 500, 502, 503, 504}
            except URLError as exc:
                last_error = exc
                should_retry = True
            except json.JSONDecodeError as exc:
                raise DeepSeekDecisionError(f"DeepSeek response was not valid JSON: {exc.msg}") from exc

            if attempt >= self.config.max_retries or not should_retry:
                break
            time.sleep(0.5 * (attempt + 1))

        if isinstance(last_error, HTTPError):
            raise DeepSeekDecisionError(f"DeepSeek API returned HTTP {last_error.code}") from last_error
        if isinstance(last_error, URLError):
            raise DeepSeekDecisionError(f"DeepSeek API request failed: {last_error.reason}") from last_error
        raise DeepSeekDecisionError("DeepSeek API request failed")


def _append_ds_request(service: LedgerService, payload: dict[str, Any]) -> None:
    append_jsonl(service.paths.ds_requests, payload)


def _append_ds_decision(service: LedgerService, payload: dict[str, Any]) -> None:
    append_jsonl(service.paths.ds_decisions, payload)


def append_ds_rejection(
    state_dir: Path | str,
    *,
    timestamp: str | None = None,
    source: str,
    reason: str,
    request_id: str | None = None,
    decision_id: str | None = None,
    details: dict[str, Any] | None = None,
    status: str = "rejected",
) -> dict[str, Any]:
    service = LedgerService(state_dir)
    entry = {
        "rejection_id": _request_id("DSX"),
        "timestamp": timestamp or now_iso(),
        "source": source,
        "status": status,
        "reason": reason,
        "request_id": request_id,
        "decision_id": decision_id,
        "details": details or {},
        "summary": reason,
    }
    append_jsonl(service.paths.ds_rejections, entry)
    return entry


def load_latest_ds_decision(state_dir: Path | str) -> dict[str, Any] | None:
    payload = read_last_jsonl(LedgerService(state_dir).paths.ds_decisions)
    return payload if isinstance(payload, dict) else None


def load_ds_decision_by_id(state_dir: Path | str, decision_id: str) -> dict[str, Any] | None:
    rows = read_jsonl(LedgerService(state_dir).paths.ds_decisions)
    normalized_id = str(decision_id).strip()
    for row in reversed(rows):
        if isinstance(row, dict) and str(row.get("decision_id", "")).strip() == normalized_id:
            return row
    return None


def load_latest_ds_rejection(state_dir: Path | str) -> dict[str, Any] | None:
    payload = read_last_jsonl(LedgerService(state_dir).paths.ds_rejections)
    return payload if isinstance(payload, dict) else None


def load_latest_ds_approval(state_dir: Path | str) -> dict[str, Any] | None:
    payload = read_last_jsonl(LedgerService(state_dir).paths.ds_approvals)
    return payload if isinstance(payload, dict) else None


def load_latest_active_ds_approval(state_dir: Path | str) -> dict[str, Any] | None:
    rows = read_jsonl(LedgerService(state_dir).paths.ds_approvals)
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "")).strip().lower()
        if status == "approved":
            return row
        if status in {"consumed", "revoked"}:
            return None
    return None


def deepseek_mode(state_dir: Path | str) -> str:
    if load_latest_active_ds_approval(state_dir) is not None:
        return "approval"
    config = load_deepseek_config()
    return "shadow" if config.enabled else "disabled"


def summarize_ds_approval(entry: dict[str, Any] | None) -> str | None:
    if entry is None:
        return None
    decision_id = str(entry.get("decision_id", "")).strip() or "n/a"
    status = str(entry.get("status", "")).strip() or "unknown"
    return f"{status} {decision_id}"


def _conversion_snapshot(
    service: LedgerService,
    *,
    timestamp: str,
) -> tuple[dict[str, Decimal], dict[str, str], Decimal]:
    snapshot = service.build_snapshot(timestamp=timestamp)
    positions = service.load_positions()
    current_weights: dict[str, Decimal] = {}
    current_stops: dict[str, str] = {}
    for symbol, position in positions.items():
        mark = snapshot.marks.get(symbol, position.last_price)
        market_value = position.market_value(mark)
        current_weights[symbol] = quantize_8(market_value / snapshot.nav) if snapshot.nav > 0 else Decimal("0")
        if position.stop_loss is not None:
            current_stops[symbol] = decimal_to_str(position.stop_loss)
    return current_weights, current_stops, snapshot.nav


def _conversion_rationale(decision: dict[str, Any], *, implicit: bool = False) -> str:
    if implicit:
        return "Implicit hold to preserve an existing position because the DS plan omitted this symbol."
    parts = [
        f"action={decision['action']}",
        f"confidence={decision['confidence']}",
        f"entry={decision['entry_reason']}",
        f"invalidation={decision['invalidation']}",
        f"stop_loss_pct={decision['stop_loss_pct']}",
        f"take_profit_pct={decision['take_profit_pct']}",
    ]
    return " | ".join(parts)


def build_execution_preview(
    *,
    state_dir: Path | str,
    decision_payload: dict[str, Any],
    timestamp: str | None = None,
) -> dict[str, Any]:
    run_time = timestamp or now_iso()
    service = LedgerService(state_dir)
    positions = service.load_positions()
    current_weights, current_stops, nav = _conversion_snapshot(service, timestamp=run_time)
    risk_config = service.load_risk_config()
    max_weight = risk_config.max_position_weight_pct
    max_gross = risk_config.max_gross_exposure_pct
    max_positions = risk_config.max_concurrent_positions

    decisions = decision_payload.get("decisions", [])
    if not isinstance(decisions, list):
        decisions = []
    explicit_symbols: set[str] = set()
    explicit_targets: dict[str, Decimal] = {}
    target_metadata: dict[str, dict[str, str]] = {}
    buy_base_weights: dict[str, Decimal] = {}
    buy_delta_targets: dict[str, Decimal] = {}
    reserved_weight = Decimal("0")
    adjustments: list[str] = []

    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        symbol = normalize_symbol(str(decision["symbol"]))
        explicit_symbols.add(symbol)
        action = str(decision["action"])
        requested_target = to_decimal(decision["target_weight"])
        current_weight = current_weights.get(symbol, Decimal("0"))
        if action == "hold":
            if symbol in positions and current_weight > 0:
                explicit_targets[symbol] = current_weight
                reserved_weight += current_weight
            target_metadata[symbol] = {
                "action": action,
                "confidence": str(decision["confidence"]),
                "rationale": _conversion_rationale(decision),
                "stop_loss_pct": str(decision["stop_loss_pct"]),
                "take_profit_pct": str(decision["take_profit_pct"]),
                "current_stop_loss": current_stops.get(symbol, ""),
            }
            continue

        if action == "buy" and requested_target < current_weight:
            raise DeepSeekDecisionError(
                f"buy action for {symbol} would reduce weight from {decimal_to_str(current_weight)} to {decision['target_weight']}"
            )
        if action == "sell" and requested_target > current_weight:
            raise DeepSeekDecisionError(
                f"sell action for {symbol} would increase weight from {decimal_to_str(current_weight)} to {decision['target_weight']}"
            )

        target = requested_target
        if target > max_weight:
            adjustments.append(
                f"{symbol} target_weight clipped from {decimal_to_str(target)} to risk max {decimal_to_str(max_weight)}"
            )
            target = max_weight

        target_metadata[symbol] = {
            "action": action,
            "confidence": str(decision["confidence"]),
            "rationale": _conversion_rationale(decision),
            "stop_loss_pct": str(decision["stop_loss_pct"]),
            "take_profit_pct": str(decision["take_profit_pct"]),
            "current_stop_loss": current_stops.get(symbol, ""),
        }
        if action == "buy":
            buy_base_weights[symbol] = current_weight
            if current_weight > 0:
                reserved_weight += current_weight
            buy_delta_targets[symbol] = max(Decimal("0"), quantize_8(target - current_weight))
            continue
        if target > 0:
            explicit_targets[symbol] = target
            reserved_weight += target

    for symbol in sorted(positions):
        if symbol in explicit_symbols:
            continue
        current_weight = current_weights.get(symbol, Decimal("0"))
        if current_weight <= 0:
            continue
        explicit_targets[symbol] = current_weight
        reserved_weight += current_weight
        target_metadata[symbol] = {
            "action": "hold",
            "confidence": "1",
            "rationale": _conversion_rationale({}, implicit=True),
            "stop_loss_pct": "0",
            "take_profit_pct": "0",
            "current_stop_loss": current_stops.get(symbol, ""),
        }

    buy_budget = max(Decimal("0"), quantize_8(max_gross - reserved_weight))
    buy_total = sum(buy_delta_targets.values(), Decimal("0"))
    scaled_buy_targets = {symbol: buy_base_weights.get(symbol, Decimal("0")) + delta for symbol, delta in buy_delta_targets.items()}
    if buy_total > buy_budget and buy_total > 0:
        scale = quantize_8(buy_budget / buy_total) if buy_budget > 0 else Decimal("0")
        adjustments.append(
            "buy targets scaled to fit remaining gross-exposure budget "
            + f"({decimal_to_str(buy_total)} -> {decimal_to_str(buy_budget)})"
        )
        scaled_buy_targets = {
            symbol: quantize_8(buy_base_weights.get(symbol, Decimal("0")) + (weight * scale))
            for symbol, weight in buy_delta_targets.items()
        }

    candidate_targets: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    for symbol in sorted(set(explicit_targets) | set(scaled_buy_targets) | explicit_symbols):
        weight = explicit_targets.get(symbol, scaled_buy_targets.get(symbol, Decimal("0")))
        meta = target_metadata.get(symbol, {})
        if symbol in scaled_buy_targets:
            weight = scaled_buy_targets[symbol]
        if symbol in explicit_targets and symbol in scaled_buy_targets:
            weight = scaled_buy_targets[symbol]
        if weight > 0:
            candidate_targets.append(
                {
                    "symbol": symbol,
                    "target_weight": decimal_to_str(weight),
                    "rationale": meta.get("rationale", ""),
                    "action": meta.get("action", "hold"),
                    "confidence": meta.get("confidence", "1"),
                    "stop_loss_pct": meta.get("stop_loss_pct", "0"),
                    "take_profit_pct": meta.get("take_profit_pct", "0"),
                }
            )
        signals.append(
            {
                "symbol": symbol,
                "signal": meta.get("action", "hold"),
                "observations": 0,
                "latest_price": "0",
                "momentum": "0",
                "ema_slope": "0",
                "confidence": meta.get("confidence", "1"),
            }
        )

    candidate_targets.sort(
        key=lambda item: (
            0 if current_weights.get(item["symbol"], Decimal("0")) > 0 else 1,
            -to_decimal(item.get("confidence", "0")),
            -to_decimal(item.get("target_weight", "0")),
            item["symbol"],
        )
    )
    targets = candidate_targets[:max_positions]
    dropped_targets = candidate_targets[max_positions:]
    if dropped_targets:
        adjustments.append(
            "targets clipped to max concurrent positions "
            + f"({len(candidate_targets)} -> {len(targets)})"
        )
    dropped_symbols = {item["symbol"] for item in dropped_targets}
    if dropped_symbols:
        signals = [row for row in signals if row["symbol"] not in dropped_symbols]

    target_weights = sum((to_decimal(item["target_weight"]) for item in targets), Decimal("0"))
    return {
        "timestamp": run_time,
        "nav": decimal_to_str(nav),
        "reserved_weight": decimal_to_str(reserved_weight),
        "target_weight_total": decimal_to_str(target_weights),
        "buy_budget": decimal_to_str(buy_budget),
        "targets": targets,
        "signals": signals,
        "adjustments": adjustments,
    }


def run_deepseek_shadow(
    *,
    state_dir: Path | str,
    source: str = "cli.ds-shadow-run",
    timestamp: str | None = None,
    plan_bias: str = "cautious",
) -> DeepSeekShadowRunResult:
    run_time = timestamp or now_iso()
    service = LedgerService(state_dir)
    config = load_deepseek_config()
    request_id = _request_id("DSR")
    if not config.enabled:
        request_entry = {
            "request_id": request_id,
            "timestamp": run_time,
            "source": source,
            "provider": "deepseek",
            "enabled": config.enabled,
            "model": config.model,
            "base_url": config.base_url,
            "messages": [],
            "context_meta": {},
        }
        _append_ds_request(service, request_entry)
        rejection = append_ds_rejection(
            state_dir,
            timestamp=run_time,
            source=source,
            reason=config.disabled_reason or "DeepSeek is disabled",
            request_id=request_id,
            details={"status": "noop"},
            status="noop",
        )
        return DeepSeekShadowRunResult(
            status="noop",
            reason=rejection["reason"],
            request_entry=request_entry,
            rejection_entry=rejection,
        )

    try:
        context = build_deepseek_context(state_dir, timestamp=run_time)
    except Exception as exc:  # noqa: BLE001
        request_entry = {
            "request_id": request_id,
            "timestamp": run_time,
            "source": source,
            "provider": "deepseek",
            "enabled": config.enabled,
            "model": config.model,
            "base_url": config.base_url,
            "messages": [],
            "context_meta": {},
        }
        _append_ds_request(service, request_entry)
        rejection = append_ds_rejection(
            state_dir,
            timestamp=run_time,
            source=source,
            reason=str(exc),
            request_id=request_id,
            details={"stage": "context-build"},
        )
        return DeepSeekShadowRunResult(
            status="rejected",
            reason=str(exc),
            request_entry=request_entry,
            rejection_entry=rejection,
        )

    request_entry = {
        "request_id": request_id,
        "timestamp": run_time,
        "source": source,
        "provider": "deepseek",
        "enabled": config.enabled,
        "model": config.model,
        "base_url": config.base_url,
        "messages": _build_messages(context, plan_bias=plan_bias),
        "context_meta": {
            "market_timestamp": context["market"].get("timestamp"),
            "signal_timestamp": context["signals"].get("timestamp"),
            "position_count": len(context["portfolio"]["positions"]),
            "tracked_symbol_count": len(context["tracked_symbols"]),
            "plan_bias": plan_bias,
        },
    }
    _append_ds_request(service, request_entry)

    try:
        client_result = DeepSeekClient(config).create_plan(context=context, plan_bias=plan_bias)
        normalized_payload = validate_deepseek_payload(
            client_result["parsed_json"],
            known_symbols=set(context["tracked_symbols"]),
        )
        preview = build_execution_preview(
            state_dir=state_dir,
            decision_payload=normalized_payload,
            timestamp=run_time,
        )
    except Exception as exc:  # noqa: BLE001
        rejection = append_ds_rejection(
            state_dir,
            timestamp=run_time,
            source=source,
            reason=str(exc),
            request_id=request_id,
        )
        return DeepSeekShadowRunResult(
            status="rejected",
            reason=str(exc),
            request_entry=request_entry,
            rejection_entry=rejection,
        )

    decision_entry = {
        "decision_id": _request_id("DSD"),
        "request_id": request_id,
        "timestamp": run_time,
        "source": source,
        "provider": "deepseek",
        "model": config.model,
        "base_url": config.base_url,
        "response_id": client_result.get("response_id"),
        "status": "validated",
        "plan_bias": plan_bias,
        "summary": _summary_from_payload(normalized_payload),
        "market_regime": normalized_payload["market_regime"],
        "global_risk_mode": normalized_payload["global_risk_mode"],
        "market_timestamp": context["market"].get("timestamp"),
        "signal_timestamp": context["signals"].get("timestamp"),
        "decision_count": len(normalized_payload["decisions"]),
        "no_trade_reason": normalized_payload.get("no_trade_reason"),
        "payload": normalized_payload,
        "execution_preview": preview,
    }
    _append_ds_decision(service, decision_entry)
    return DeepSeekShadowRunResult(
        status="validated",
        reason=decision_entry["summary"],
        request_entry=request_entry,
        decision_entry=decision_entry,
    )


def approve_latest_deepseek_decision(
    state_dir: Path | str,
    *,
    source: str = "cli.ds-approve-latest",
    timestamp: str | None = None,
) -> dict[str, Any]:
    decision_entry = load_latest_ds_decision(state_dir)
    if decision_entry is None:
        raise FileNotFoundError("no validated DeepSeek decision is available")

    service = LedgerService(state_dir)
    approval_entry = {
        "approval_id": _request_id("DSA"),
        "timestamp": timestamp or now_iso(),
        "source": source,
        "status": "approved",
        "decision_id": str(decision_entry.get("decision_id", "")),
        "decision_timestamp": str(decision_entry.get("timestamp", "")),
        "decision_summary": str(decision_entry.get("summary", "")),
    }
    append_jsonl(service.paths.ds_approvals, approval_entry)
    return approval_entry


def mark_latest_approval_consumed(
    state_dir: Path | str,
    *,
    execution_id: str,
    source: str = "cli.execute-sim",
    timestamp: str | None = None,
) -> dict[str, Any]:
    approval_entry = load_latest_active_ds_approval(state_dir)
    if approval_entry is None:
        raise FileNotFoundError("no active DeepSeek approval is available")

    service = LedgerService(state_dir)
    consumed_entry = {
        "approval_id": str(approval_entry.get("approval_id", "")),
        "timestamp": timestamp or now_iso(),
        "source": source,
        "status": "consumed",
        "decision_id": str(approval_entry.get("decision_id", "")),
        "decision_timestamp": str(approval_entry.get("decision_timestamp", "")),
        "execution_id": execution_id,
        "decision_summary": str(approval_entry.get("decision_summary", "")),
    }
    append_jsonl(service.paths.ds_approvals, consumed_entry)
    return consumed_entry


def build_signal_entry_from_ds_decision(
    *,
    state_dir: Path | str,
    decision_entry: dict[str, Any],
    source: str = "cli.execute-sim",
    timestamp: str | None = None,
) -> dict[str, Any]:
    if not isinstance(decision_entry, dict) or not isinstance(decision_entry.get("payload"), dict):
        raise DeepSeekDecisionError("DeepSeek decision entry is malformed")

    preview = build_execution_preview(
        state_dir=state_dir,
        decision_payload=decision_entry["payload"],
        timestamp=timestamp,
    )
    payload = decision_entry["payload"]
    signals = preview["signals"]
    targets = preview["targets"]
    decision_summary = _summary_from_payload(payload)
    no_trade_reason = payload.get("no_trade_reason")
    if no_trade_reason:
        decision_summary = f"{decision_summary} | no_trade_reason={no_trade_reason}"
    return {
        "timestamp": timestamp or now_iso(),
        "source": source,
        "decision_source": "ds-approved",
        "decision_id": decision_entry.get("decision_id"),
        "market_timestamp": decision_entry.get("market_timestamp", decision_entry.get("timestamp", "")),
        "lookback_points": 0,
        "symbols": [item["symbol"] for item in signals],
        "signal_count": len(signals),
        "bullish_count": len([item for item in signals if item["signal"] == "buy"]),
        "bearish_count": len([item for item in signals if item["signal"] == "sell"]),
        "status": "watch" if no_trade_reason else "ok",
        "summary": f"DS approved {decision_summary}",
        "signals": signals,
        "targets": targets,
        "market_regime": payload.get("market_regime"),
        "global_risk_mode": payload.get("global_risk_mode"),
        "no_trade_reason": no_trade_reason,
        "ds_adjustments": preview["adjustments"],
    }
