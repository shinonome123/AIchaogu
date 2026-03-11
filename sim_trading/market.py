from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sim_trading.ledger import LedgerService
from sim_trading.models import decimal_to_str, normalize_symbol, now_iso, quantize_8, to_decimal
from sim_trading.storage import StoragePaths, append_jsonl, read_json, read_jsonl, read_last_jsonl
from sim_trading.strategy import EqualWeightMomentumStrategy, MarketSignal

DEFAULT_MARKET_SOURCE = "binance"
DEFAULT_MARKET_API_ROOT = "https://api.binance.com"


@dataclass(frozen=True)
class MarketFetchResult:
    entry: dict[str, object]
    market_prices: dict[str, dict[str, str]]


@dataclass(frozen=True)
class SignalRunResult:
    entry: dict[str, object]


def _dedupe_symbols(symbols: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_symbol in symbols:
        symbol = normalize_symbol(raw_symbol)
        if symbol not in seen:
            ordered.append(symbol)
            seen.add(symbol)
    return ordered


def resolve_market_symbols(state_dir: Path | str, explicit_symbols: list[str] | None = None) -> list[str]:
    if explicit_symbols:
        symbols = _dedupe_symbols(explicit_symbols)
        if symbols:
            return symbols

    paths = StoragePaths(Path(state_dir))
    config_payload = read_json(paths.config, default={}) or {}
    strategy_payload = config_payload.get("strategy", {}) if isinstance(config_payload, dict) else {}
    configured = strategy_payload.get("symbols") or strategy_payload.get("watchlist") or []
    if isinstance(configured, list):
        symbols = _dedupe_symbols([str(item) for item in configured if str(item).strip()])
        if symbols:
            return symbols

    positions_payload = read_json(paths.positions, default=[]) or []
    if isinstance(positions_payload, list):
        symbols = _dedupe_symbols([str(item.get("symbol", "")) for item in positions_payload if item.get("symbol")])
        if symbols:
            return symbols

    raise ValueError("no symbols configured; pass --symbol or add strategy.symbols to config.json")


def _binance_pair(symbol: str) -> str:
    pair = symbol.replace("/", "").replace("-", "").upper()
    if not pair:
        raise ValueError(f"invalid symbol '{symbol}'")
    return pair


def persist_market_feed_entry(
    *,
    state_dir: Path | str,
    entry: dict[str, object],
    append_feed: bool = True,
) -> dict[str, dict[str, str]]:
    service = LedgerService(state_dir)
    market_prices = service.load_market_prices()
    prices = entry.get("prices", {})
    if not isinstance(prices, dict):
        raise ValueError("market feed entry must include a prices object")
    for symbol, item in prices.items():
        if not isinstance(item, dict) or "price" not in item:
            continue
        market_prices[normalize_symbol(symbol)] = {
            "price": str(item["price"]),
            "timestamp": str(item.get("timestamp", entry.get("timestamp", ""))),
        }
    service.save_market_prices(market_prices)
    if append_feed:
        append_jsonl(service.paths.market_feed, entry)
    return market_prices


def fetch_market_snapshot(
    *,
    state_dir: Path | str,
    symbols: list[str],
    source: str = DEFAULT_MARKET_SOURCE,
    api_root: str = DEFAULT_MARKET_API_ROOT,
    timestamp: str | None = None,
    timeout_seconds: int = 10,
    append_feed: bool = True,
) -> MarketFetchResult:
    resolved_symbols = _dedupe_symbols(symbols)
    if not resolved_symbols:
        raise ValueError("at least one market symbol is required")
    normalized_source = source.strip().lower()
    if normalized_source != DEFAULT_MARKET_SOURCE:
        raise ValueError(f"unsupported source '{source}'")

    fetch_time = timestamp or now_iso()
    prices: dict[str, dict[str, str]] = {}
    for symbol in resolved_symbols:
        exchange_symbol = _binance_pair(symbol)
        request = Request(
            f"{api_root.rstrip('/')}/api/v3/ticker/price?symbol={quote(exchange_symbol)}",
            headers={"User-Agent": "sim-trading/0.1"},
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"market fetch failed for {symbol}: HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"market fetch failed for {symbol}: {exc.reason}") from exc

        if not isinstance(payload, dict) or "price" not in payload:
            raise RuntimeError(f"market fetch failed for {symbol}: unexpected payload")

        price = quantize_8(to_decimal(payload["price"]))
        prices[symbol] = {
            "symbol": symbol,
            "exchange_symbol": str(payload.get("symbol", exchange_symbol)),
            "price": decimal_to_str(price),
            "timestamp": fetch_time,
            "source": normalized_source,
        }

    entry = {
        "timestamp": fetch_time,
        "source": normalized_source,
        "api_root": api_root.rstrip("/"),
        "symbols": resolved_symbols,
        "prices": prices,
    }

    market_prices = persist_market_feed_entry(state_dir=state_dir, entry=entry, append_feed=append_feed)

    return MarketFetchResult(entry=entry, market_prices=market_prices)


def load_latest_market_fetch(state_dir: Path | str) -> dict[str, object] | None:
    paths = StoragePaths(Path(state_dir))
    payload = read_last_jsonl(paths.market_feed)
    return payload if isinstance(payload, dict) else None


def load_latest_signal_run(state_dir: Path | str) -> dict[str, object] | None:
    paths = StoragePaths(Path(state_dir))
    payload = read_last_jsonl(paths.signal_runs)
    return payload if isinstance(payload, dict) else None


def _ema_series(values: list[Decimal], period: int) -> list[Decimal]:
    if not values:
        return []
    alpha = Decimal("2") / (Decimal(period) + Decimal("1"))
    ema_values = [quantize_8(values[0])]
    for value in values[1:]:
        ema_values.append(quantize_8((value * alpha) + (ema_values[-1] * (Decimal("1") - alpha))))
    return ema_values


def _signal_label(momentum: Decimal, ema_slope: Decimal, observations: int) -> str:
    if observations < 2:
        return "insufficient"
    if momentum > 0 and ema_slope > 0:
        return "bullish"
    if momentum < 0 and ema_slope < 0:
        return "bearish"
    return "flat"


def _strategy_from_config(config_payload: dict[str, object]) -> EqualWeightMomentumStrategy:
    strategy_payload = config_payload.get("strategy", {}) if isinstance(config_payload, dict) else {}
    strategy_name = str(strategy_payload.get("name", "equal_weight_momentum"))
    if strategy_name != "equal_weight_momentum":
        raise ValueError(f"unsupported strategy '{strategy_name}'")
    min_momentum = to_decimal(strategy_payload.get("min_momentum", "0"))
    return EqualWeightMomentumStrategy(min_momentum=min_momentum)


def _configured_signal_symbols(config_payload: dict[str, object]) -> set[str] | None:
    strategy_payload = config_payload.get("strategy", {}) if isinstance(config_payload, dict) else {}
    configured = strategy_payload.get("symbols") or strategy_payload.get("watchlist") or []
    if not isinstance(configured, list):
        return None
    symbols = {
        normalize_symbol(str(item))
        for item in configured
        if str(item).strip()
    }
    return symbols or None


def build_signal_run_entry(
    *,
    config_payload: dict[str, object],
    feed_rows: list[dict[str, Any]],
    nav: Decimal,
    risk_config,
    source: str,
    lookback_points: int,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if lookback_points < 2:
        raise ValueError("lookback points must be at least 2")
    if len(feed_rows) < lookback_points:
        raise ValueError(f"need at least {lookback_points} market-feed rows")

    recent_rows = feed_rows[-lookback_points:]
    latest_row = recent_rows[-1]
    configured_symbols = _configured_signal_symbols(config_payload)
    price_history: dict[str, list[Decimal]] = {}
    for row in recent_rows:
        prices = row.get("prices", {})
        if not isinstance(prices, dict):
            continue
        for symbol, payload in prices.items():
            normalized_symbol = normalize_symbol(symbol)
            if configured_symbols is not None and normalized_symbol not in configured_symbols:
                continue
            if not isinstance(payload, dict) or "price" not in payload:
                continue
            price_history.setdefault(normalized_symbol, []).append(to_decimal(payload["price"]))

    signals: list[MarketSignal] = []
    signal_rows: list[dict[str, str | int]] = []
    bullish_count = 0
    bearish_count = 0
    for symbol in sorted(price_history):
        series = price_history[symbol]
        observations = len(series)
        earliest = series[0]
        latest = series[-1]
        momentum = quantize_8((latest / earliest) - Decimal("1")) if observations >= 2 and earliest > 0 else Decimal("0")
        ema_values = _ema_series(series, period=min(5, observations))
        ema_slope = quantize_8(ema_values[-1] - ema_values[-2]) if len(ema_values) >= 2 else Decimal("0")
        label = _signal_label(momentum, ema_slope, observations)
        if label == "bullish":
            bullish_count += 1
        elif label == "bearish":
            bearish_count += 1
        signal = MarketSignal(symbol=symbol, momentum_7d=momentum, ema_slope=ema_slope)
        signals.append(signal)
        signal_rows.append(
            {
                "symbol": symbol,
                "observations": observations,
                "latest_price": decimal_to_str(latest),
                "momentum": decimal_to_str(momentum),
                "ema_slope": decimal_to_str(ema_slope),
                "signal": label,
            }
        )

    strategy = _strategy_from_config(config_payload)
    targets = strategy.generate_targets(
        nav=nav,
        signals=signals,
        risk_config=risk_config,
    )

    run_time = timestamp or now_iso()
    status = "ok" if bullish_count else "watch"
    return {
        "timestamp": run_time,
        "source": source,
        "market_timestamp": str(latest_row.get("timestamp", "")),
        "lookback_points": lookback_points,
        "symbols": [row["symbol"] for row in signal_rows],
        "signal_count": len(signal_rows),
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "status": status,
        "summary": f"{bullish_count} bullish / {bearish_count} bearish / {len(signal_rows)} total",
        "signals": signal_rows,
        "targets": [
            {
                "symbol": target.symbol,
                "target_weight": decimal_to_str(target.target_weight),
                "rationale": target.rationale,
            }
            for target in targets
        ],
    }


def run_signal_snapshot(
    *,
    state_dir: Path | str,
    source: str = "market-feed",
    lookback_points: int = 6,
    timestamp: str | None = None,
) -> SignalRunResult:
    if lookback_points < 2:
        raise ValueError("lookback points must be at least 2")

    service = LedgerService(state_dir)
    feed_rows = [item for item in read_jsonl(service.paths.market_feed) if isinstance(item, dict)]
    if not feed_rows:
        raise FileNotFoundError(f"market feed is empty: {service.paths.market_feed}")
    config_payload = read_json(service.paths.config, default={}) or {}
    snapshot = service.build_snapshot(timestamp=timestamp or now_iso())
    entry = build_signal_run_entry(
        config_payload=config_payload,
        feed_rows=feed_rows,
        nav=snapshot.nav,
        risk_config=service.load_risk_config(),
        source=source,
        lookback_points=lookback_points,
        timestamp=timestamp,
    )
    append_jsonl(service.paths.signal_runs, entry)
    return SignalRunResult(entry=entry)
