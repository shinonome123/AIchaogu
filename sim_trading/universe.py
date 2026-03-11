from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sim_trading.market import persist_market_feed_entry
from sim_trading.models import decimal_to_str, now_iso, quantize_8, to_decimal
from sim_trading.storage import StoragePaths, append_jsonl, read_json, read_last_jsonl, write_json

DEFAULT_UNIVERSE_SOURCE = "binance"
DEFAULT_UNIVERSE_API_ROOT = "https://api.binance.com"
DEFAULT_UNIVERSE_TIMEOUT_SECONDS = 20
DEFAULT_TOP_LIMIT = 120
DEFAULT_DS_LIMIT = 30
DEFAULT_MIN_LISTING_AGE_DAYS = 30
DEFAULT_MIN_QUOTE_VOLUME = Decimal("5000000")
DEFAULT_MIN_TRADE_COUNT = 2000
DEFAULT_MAX_SPREAD_PCT = Decimal("0.01")
DEFAULT_LISTING_AGE_WORKERS = 12

LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
STABLE_BASE_ASSETS = {
    "USDT",
    "USDC",
    "FDUSD",
    "TUSD",
    "BUSD",
    "USDP",
    "USDS",
    "DAI",
    "SUSD",
    "PYUSD",
    "EURS",
}
UNIVERSE_RANKING_RULE = (
    "Sort descending by 24h quote volume, descending by trade count, ascending by quoted spread, "
    "descending by listing age, then symbol."
)


@dataclass(frozen=True)
class UniverseRefreshResult:
    entry: dict[str, Any]
    universe_all: dict[str, Any]
    universe_filtered: dict[str, Any]
    universe_top120: dict[str, Any]
    universe_top30: dict[str, Any]


def _request_json(url: str, *, timeout_seconds: int) -> Any:
    request = Request(url, headers={"User-Agent": "sim-trading/0.4"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"universe request failed for {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"universe request failed for {url}: {exc.reason}") from exc


def _spot_symbol(item: dict[str, Any]) -> bool:
    status_ok = str(item.get("status", "")).upper() == "TRADING"
    quote_ok = str(item.get("quoteAsset", "")).upper() == "USDT"
    if not (status_ok and quote_ok):
        return False
    permissions = item.get("permissions")
    if isinstance(permissions, list) and permissions:
        return "SPOT" in {str(value).upper() for value in permissions}
    if item.get("isSpotTradingAllowed") is not None:
        return bool(item.get("isSpotTradingAllowed"))
    return True


def _leveraged_token(base_asset: str, symbol: str) -> bool:
    upper_base = base_asset.upper()
    upper_symbol = symbol.upper()
    return any(upper_base.endswith(marker) or upper_symbol.startswith(marker) for marker in LEVERAGED_SUFFIXES)


def _stable_stable(base_asset: str) -> bool:
    return base_asset.upper() in STABLE_BASE_ASSETS


def _spread_pct(bid_price: Decimal, ask_price: Decimal) -> Decimal | None:
    if bid_price <= 0 or ask_price <= 0 or ask_price < bid_price:
        return None
    midpoint = (bid_price + ask_price) / Decimal("2")
    if midpoint <= 0:
        return None
    return quantize_8((ask_price - bid_price) / midpoint)


def _listing_age_days(onboard_date_ms: int | None, *, timestamp: str) -> int | None:
    if onboard_date_ms is None or onboard_date_ms <= 0:
        return None
    listed_at = datetime.fromtimestamp(onboard_date_ms / 1000, tz=datetime.now().astimezone().tzinfo)
    run_time = datetime.fromisoformat(timestamp)
    return max(0, (run_time - listed_at).days)


def _resolve_klines_listing_age(
    *,
    api_root: str,
    symbols: list[str],
    timestamp: str,
    timeout_seconds: int,
    max_workers: int,
) -> dict[str, int | None]:
    if not symbols:
        return {}

    run_time = datetime.fromisoformat(timestamp)

    def fetch_symbol(symbol: str) -> tuple[str, int | None]:
        payload = _request_json(
            f"{api_root.rstrip('/')}/api/v3/klines?symbol={quote(symbol)}&interval=1d&limit=1&startTime=0",
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(payload, list) or not payload:
            return symbol, None
        first_row = payload[0]
        if not isinstance(first_row, list) or not first_row:
            return symbol, None
        try:
            open_time_ms = int(first_row[0])
        except (TypeError, ValueError):
            return symbol, None
        listed_at = datetime.fromtimestamp(open_time_ms / 1000, tz=run_time.tzinfo)
        return symbol, max(0, (run_time - listed_at).days)

    ages: dict[str, int | None] = {}
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        future_map = {executor.submit(fetch_symbol, symbol): symbol for symbol in symbols}
        for future in as_completed(future_map):
            symbol = future_map[future]
            try:
                resolved_symbol, age_days = future.result()
            except Exception:  # noqa: BLE001
                ages[symbol] = None
                continue
            ages[resolved_symbol] = age_days
    return ages


def _item_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": item["symbol"],
        "exchange_symbol": item["exchange_symbol"],
        "base_asset": item["base_asset"],
        "quote_asset": item["quote_asset"],
        "listing_age_days": item["listing_age_days"],
        "quote_volume_24h": decimal_to_str(item["quote_volume_24h"]),
        "trade_count": item["trade_count"],
        "last_price": decimal_to_str(item["last_price"]),
        "bid_price": decimal_to_str(item["bid_price"]),
        "ask_price": decimal_to_str(item["ask_price"]),
        "spread_pct": decimal_to_str(item["spread_pct"]) if item["spread_pct"] is not None else None,
        "leveraged_token": item["leveraged_token"],
        "stable_stable": item["stable_stable"],
        "passed_filters": item["passed_filters"],
        "excluded_reasons": list(item["excluded_reasons"]),
        "rank": item.get("rank"),
    }


def refresh_universe(
    *,
    state_dir: Path | str,
    source: str = DEFAULT_UNIVERSE_SOURCE,
    api_root: str = DEFAULT_UNIVERSE_API_ROOT,
    timestamp: str | None = None,
    timeout_seconds: int = DEFAULT_UNIVERSE_TIMEOUT_SECONDS,
    top_limit: int = DEFAULT_TOP_LIMIT,
    ds_limit: int = DEFAULT_DS_LIMIT,
    min_listing_age_days: int = DEFAULT_MIN_LISTING_AGE_DAYS,
    min_quote_volume: Decimal = DEFAULT_MIN_QUOTE_VOLUME,
    min_trade_count: int = DEFAULT_MIN_TRADE_COUNT,
    max_spread_pct: Decimal = DEFAULT_MAX_SPREAD_PCT,
    listing_age_workers: int = DEFAULT_LISTING_AGE_WORKERS,
) -> UniverseRefreshResult:
    normalized_source = source.strip().lower()
    if normalized_source != DEFAULT_UNIVERSE_SOURCE:
        raise ValueError(f"unsupported universe source '{source}'")

    run_time = timestamp or now_iso()
    exchange_info = _request_json(
        f"{api_root.rstrip('/')}/api/v3/exchangeInfo",
        timeout_seconds=timeout_seconds,
    )
    ticker_24h = _request_json(
        f"{api_root.rstrip('/')}/api/v3/ticker/24hr",
        timeout_seconds=timeout_seconds,
    )
    book_tickers = _request_json(
        f"{api_root.rstrip('/')}/api/v3/ticker/bookTicker",
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(exchange_info, dict) or not isinstance(exchange_info.get("symbols"), list):
        raise RuntimeError("exchangeInfo payload did not include a symbols array")
    if not isinstance(ticker_24h, list):
        raise RuntimeError("24hr ticker payload must be an array")
    if not isinstance(book_tickers, list):
        raise RuntimeError("bookTicker payload must be an array")

    by_symbol: dict[str, dict[str, Any]] = {}
    for row in exchange_info["symbols"]:
        if not isinstance(row, dict) or not _spot_symbol(row):
            continue
        exchange_symbol = str(row.get("symbol", "")).strip().upper()
        if not exchange_symbol:
            continue
        base_asset = str(row.get("baseAsset", "")).strip().upper()
        by_symbol[exchange_symbol] = {
            "symbol": f"{base_asset}/USDT",
            "exchange_symbol": exchange_symbol,
            "base_asset": base_asset,
            "quote_asset": "USDT",
            "listing_age_days": _listing_age_days(
                int(row.get("onboardDate")) if row.get("onboardDate") is not None else None,
                timestamp=run_time,
            ),
            "quote_volume_24h": Decimal("0"),
            "trade_count": 0,
            "last_price": Decimal("0"),
            "bid_price": Decimal("0"),
            "ask_price": Decimal("0"),
            "spread_pct": None,
            "leveraged_token": _leveraged_token(base_asset, exchange_symbol),
            "stable_stable": _stable_stable(base_asset),
            "passed_filters": False,
            "excluded_reasons": [],
        }

    for row in ticker_24h:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol not in by_symbol:
            continue
        by_symbol[symbol]["quote_volume_24h"] = to_decimal(row.get("quoteVolume", "0"))
        by_symbol[symbol]["trade_count"] = int(row.get("count", 0) or 0)
        by_symbol[symbol]["last_price"] = to_decimal(row.get("lastPrice", row.get("weightedAvgPrice", "0")))

    for row in book_tickers:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol not in by_symbol:
            continue
        bid_price = to_decimal(row.get("bidPrice", "0"))
        ask_price = to_decimal(row.get("askPrice", "0"))
        by_symbol[symbol]["bid_price"] = bid_price
        by_symbol[symbol]["ask_price"] = ask_price
        by_symbol[symbol]["spread_pct"] = _spread_pct(bid_price, ask_price)

    missing_listing_symbols = [
        exchange_symbol
        for exchange_symbol, item in by_symbol.items()
        if item["listing_age_days"] is None and not item["leveraged_token"] and not item["stable_stable"]
    ]
    if missing_listing_symbols:
        resolved_ages = _resolve_klines_listing_age(
            api_root=api_root,
            symbols=missing_listing_symbols,
            timestamp=run_time,
            timeout_seconds=timeout_seconds,
            max_workers=listing_age_workers,
        )
        for exchange_symbol, age_days in resolved_ages.items():
            if exchange_symbol in by_symbol:
                by_symbol[exchange_symbol]["listing_age_days"] = age_days

    all_items: list[dict[str, Any]] = []
    filtered_items: list[dict[str, Any]] = []
    for exchange_symbol in sorted(by_symbol):
        item = by_symbol[exchange_symbol]
        reasons: list[str] = []
        if item["leveraged_token"]:
            reasons.append("leveraged_token")
        if item["stable_stable"]:
            reasons.append("stable_stable")
        if item["listing_age_days"] is None or item["listing_age_days"] < min_listing_age_days:
            reasons.append("listing_age_below_threshold")
        if item["quote_volume_24h"] < min_quote_volume:
            reasons.append("quote_volume_below_threshold")
        if int(item["trade_count"]) < min_trade_count:
            reasons.append("trade_count_below_threshold")
        if item["spread_pct"] is None or item["spread_pct"] > max_spread_pct:
            reasons.append("spread_above_threshold")
        item["excluded_reasons"] = reasons
        item["passed_filters"] = not reasons
        all_items.append(dict(item))
        if item["passed_filters"]:
            filtered_items.append(dict(item))

    filtered_items.sort(
        key=lambda item: (
            -item["quote_volume_24h"],
            -int(item["trade_count"]),
            item["spread_pct"] if item["spread_pct"] is not None else Decimal("999"),
            -(item["listing_age_days"] or 0),
            item["symbol"],
        )
    )
    for index, item in enumerate(filtered_items, start=1):
        item["rank"] = index

    top120_items = [dict(item) for item in filtered_items[: max(1, top_limit)]]
    top30_items = [dict(item) for item in top120_items[: max(1, ds_limit)]]

    counts = {
        "all": len(all_items),
        "filtered": len(filtered_items),
        "top120": len(top120_items),
        "top30": len(top30_items),
    }
    common_payload = {
        "timestamp": run_time,
        "source": normalized_source,
        "api_root": api_root.rstrip("/"),
        "ranking_rule": UNIVERSE_RANKING_RULE,
        "counts": counts,
    }
    universe_all = {
        **common_payload,
        "artifact": "universe_all",
        "count": len(all_items),
        "symbols": [item["symbol"] for item in all_items],
        "items": [_item_payload(item) for item in all_items],
    }
    universe_filtered = {
        **common_payload,
        "artifact": "universe_filtered",
        "count": len(filtered_items),
        "symbols": [item["symbol"] for item in filtered_items],
        "items": [_item_payload(item) for item in filtered_items],
    }
    universe_top120 = {
        **common_payload,
        "artifact": "universe_top120",
        "count": len(top120_items),
        "symbols": [item["symbol"] for item in top120_items],
        "items": [_item_payload(item) for item in top120_items],
    }
    universe_top30 = {
        **common_payload,
        "artifact": "universe_top30",
        "count": len(top30_items),
        "symbols": [item["symbol"] for item in top30_items],
        "items": [_item_payload(item) for item in top30_items],
    }

    paths = StoragePaths(Path(state_dir))
    write_json(paths.universe_all, universe_all)
    write_json(paths.universe_filtered, universe_filtered)
    write_json(paths.universe_top120, universe_top120)
    write_json(paths.universe_top30, universe_top30)

    prices = {
        item["symbol"]: {
            "symbol": item["symbol"],
            "exchange_symbol": item["exchange_symbol"],
            "price": decimal_to_str(item["last_price"]),
            "timestamp": run_time,
            "source": "binance-universe",
        }
        for item in top120_items
        if item["last_price"] > 0
    }
    market_feed_entry = {
        "timestamp": run_time,
        "source": "binance-universe",
        "api_root": api_root.rstrip("/"),
        "symbols": list(prices),
        "prices": prices,
    }
    if prices:
        persist_market_feed_entry(state_dir=state_dir, entry=market_feed_entry)

    run_entry = {
        **common_payload,
        "top120_symbols": universe_top120["symbols"],
        "top30_symbols": universe_top30["symbols"],
        "market_feed_symbols": len(prices),
    }
    append_jsonl(paths.universe_runs, run_entry)
    return UniverseRefreshResult(
        entry=run_entry,
        universe_all=universe_all,
        universe_filtered=universe_filtered,
        universe_top120=universe_top120,
        universe_top30=universe_top30,
    )


def load_universe_artifact(state_dir: Path | str, artifact: str) -> dict[str, Any] | None:
    paths = StoragePaths(Path(state_dir))
    mapping = {
        "all": paths.universe_all,
        "filtered": paths.universe_filtered,
        "top120": paths.universe_top120,
        "top30": paths.universe_top30,
    }
    path = mapping.get(artifact)
    if path is None:
        raise ValueError(f"unknown universe artifact '{artifact}'")
    payload = read_json(path)
    return payload if isinstance(payload, dict) else None


def resolve_universe_symbols(state_dir: Path | str, artifact: str) -> list[str]:
    payload = load_universe_artifact(state_dir, artifact)
    if payload is None:
        raise FileNotFoundError(f"universe artifact '{artifact}' is missing; run universe-refresh first")
    symbols = payload.get("symbols", [])
    if not isinstance(symbols, list):
        raise ValueError(f"universe artifact '{artifact}' is malformed")
    return [str(symbol) for symbol in symbols if str(symbol).strip()]


def load_latest_universe_run(state_dir: Path | str) -> dict[str, Any] | None:
    payload = read_last_jsonl(StoragePaths(Path(state_dir)).universe_runs)
    return payload if isinstance(payload, dict) else None


def build_universe_status(state_dir: Path | str) -> dict[str, Any]:
    all_payload = load_universe_artifact(state_dir, "all")
    filtered_payload = load_universe_artifact(state_dir, "filtered")
    top120_payload = load_universe_artifact(state_dir, "top120")
    top30_payload = load_universe_artifact(state_dir, "top30")
    latest_run = load_latest_universe_run(state_dir)
    return {
        "latest_refresh_at": latest_run.get("timestamp") if latest_run else None,
        "ranking_rule": latest_run.get("ranking_rule") if latest_run else UNIVERSE_RANKING_RULE,
        "all_count": int(all_payload.get("count", 0)) if all_payload else 0,
        "filtered_count": int(filtered_payload.get("count", 0)) if filtered_payload else 0,
        "top120_count": int(top120_payload.get("count", 0)) if top120_payload else 0,
        "top30_count": int(top30_payload.get("count", 0)) if top30_payload else 0,
        "counts": {
            "all": int(all_payload.get("count", 0)) if all_payload else 0,
            "filtered": int(filtered_payload.get("count", 0)) if filtered_payload else 0,
            "top120": int(top120_payload.get("count", 0)) if top120_payload else 0,
            "top30": int(top30_payload.get("count", 0)) if top30_payload else 0,
        },
        "latest_run": latest_run,
    }
