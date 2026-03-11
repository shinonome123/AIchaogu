from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim_trading.cli import main as cli_main
from sim_trading.servers import DashboardServerConfig, make_dashboard_handler
from sim_trading.storage import read_csv_rows, read_json, read_jsonl


class FakeHTTPResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.status = 200

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class DummyServer:
    server_name = "localhost"
    server_port = 0


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli_main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def roundtrip(handler_cls: type, request_bytes: bytes) -> tuple[bytes, bytes]:
    left, right = socket.socketpair()
    response = b""

    def runner() -> None:
        handler_cls(left, ("127.0.0.1", 0), DummyServer())
        left.close()

    thread = threading.Thread(target=runner)
    thread.start()
    right.sendall(request_bytes)
    right.shutdown(socket.SHUT_WR)
    while True:
        chunk = right.recv(65535)
        if not chunk:
            break
        response += chunk
    right.close()
    thread.join(timeout=2)
    if thread.is_alive():
        raise RuntimeError("handler thread did not finish")
    head, body = response.split(b"\r\n\r\n", 1)
    return head, body


def http_request(method: str, path: str) -> bytes:
    return f"{method} {path} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode("utf-8")


def universe_symbols() -> list[str]:
    return [f"COIN{index:03d}" for index in range(1, 133)]


def build_exchange_info(run_time: str) -> dict[str, object]:
    base_time = datetime.fromisoformat(run_time)
    old_ms = int((base_time - timedelta(days=180)).timestamp() * 1000)
    new_ms = int((base_time - timedelta(days=20)).timestamp() * 1000)
    symbols: list[dict[str, object]] = []
    for index, base_asset in enumerate(universe_symbols(), start=1):
        symbols.append(
            {
                "symbol": f"{base_asset}USDT",
                "status": "TRADING",
                "baseAsset": base_asset,
                "quoteAsset": "USDT",
                "permissions": ["SPOT"],
                "onboardDate": old_ms + (index * 1000),
            }
        )
    symbols.extend(
        [
            {
                "symbol": "BTCUPUSDT",
                "status": "TRADING",
                "baseAsset": "BTCUP",
                "quoteAsset": "USDT",
                "permissions": ["SPOT"],
                "onboardDate": old_ms,
            },
            {
                "symbol": "USDCUSDT",
                "status": "TRADING",
                "baseAsset": "USDC",
                "quoteAsset": "USDT",
                "permissions": ["SPOT"],
                "onboardDate": old_ms,
            },
            {
                "symbol": "NEWCOINUSDT",
                "status": "TRADING",
                "baseAsset": "NEWCOIN",
                "quoteAsset": "USDT",
                "permissions": ["SPOT"],
                "onboardDate": new_ms,
            },
            {
                "symbol": "WIDESPREADUSDT",
                "status": "TRADING",
                "baseAsset": "WIDESPREAD",
                "quoteAsset": "USDT",
                "permissions": ["SPOT"],
                "onboardDate": old_ms,
            },
        ]
    )
    return {"timezone": "UTC", "serverTime": int(base_time.timestamp() * 1000), "symbols": symbols}


def build_24hr_tickers(step: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, base_asset in enumerate(universe_symbols(), start=1):
        last_price = 1 + (index / 50) + (step * 0.03)
        rows.append(
            {
                "symbol": f"{base_asset}USDT",
                "quoteVolume": str(140_000_000 - (index * 250_000)),
                "count": 60_000 - (index * 80),
                "lastPrice": f"{last_price:.6f}",
            }
        )
    rows.extend(
        [
            {"symbol": "BTCUPUSDT", "quoteVolume": "50000000", "count": 25000, "lastPrice": "2.0"},
            {"symbol": "USDCUSDT", "quoteVolume": "80000000", "count": 100000, "lastPrice": "1.0"},
            {"symbol": "NEWCOINUSDT", "quoteVolume": "45000000", "count": 18000, "lastPrice": "1.1"},
            {"symbol": "WIDESPREADUSDT", "quoteVolume": "60000000", "count": 30000, "lastPrice": "3.0"},
        ]
    )
    return rows


def build_book_tickers(step: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, base_asset in enumerate(universe_symbols(), start=1):
        mid = 1 + (index / 50) + (step * 0.03)
        bid = mid * 0.9995
        ask = mid * 1.0005
        rows.append(
            {
                "symbol": f"{base_asset}USDT",
                "bidPrice": f"{bid:.6f}",
                "askPrice": f"{ask:.6f}",
            }
        )
    rows.extend(
        [
            {"symbol": "BTCUPUSDT", "bidPrice": "1.9990", "askPrice": "2.0010"},
            {"symbol": "USDCUSDT", "bidPrice": "0.9999", "askPrice": "1.0001"},
            {"symbol": "NEWCOINUSDT", "bidPrice": "1.0995", "askPrice": "1.1005"},
            {"symbol": "WIDESPREADUSDT", "bidPrice": "2.70", "askPrice": "3.30"},
        ]
    )
    return rows


def fake_universe_urlopen(run_time: str, step: int):
    exchange_info = build_exchange_info(run_time)
    ticker_24h = build_24hr_tickers(step)
    book_tickers = build_book_tickers(step)

    def fake_urlopen(request, timeout=20):  # noqa: ANN001
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "/api/v3/exchangeInfo" in url:
            return FakeHTTPResponse(exchange_info)
        if "/api/v3/ticker/24hr" in url:
            return FakeHTTPResponse(ticker_24h)
        if "/api/v3/ticker/bookTicker" in url:
            return FakeHTTPResponse(book_tickers)
        raise RuntimeError(f"unexpected universe url {url}")

    return fake_urlopen


def build_ds_plan(symbols: list[str], *, aggressive: bool) -> dict[str, object]:
    decisions = []
    for index, symbol in enumerate(symbols[:12], start=1):
        decisions.append(
            {
                "symbol": symbol,
                "action": "buy",
                "target_weight": 0.10 if aggressive else 0.08,
                "confidence": max(0.4, 0.92 - (index * 0.02)),
                "entry_reason": f"{symbol} remains strong in the candidate basket.",
                "invalidation": f"{symbol} loses momentum leadership.",
                "stop_loss_pct": 0.035,
                "take_profit_pct": 0.08 if aggressive else 0.06,
            }
        )
    payload = {
        "id": f"resp-{'aggr' if aggressive else 'cons'}",
        "choices": [{"message": {"content": json.dumps({"market_regime": "trending", "global_risk_mode": "normal" if aggressive else "cautious", "decisions": decisions})}}],
    }
    return payload


def fake_ds_urlopen_factory(responses: list[dict[str, object]]):
    queue = list(responses)

    def fake_urlopen(request, timeout=20):  # noqa: ANN001
        if not queue:
            raise RuntimeError("no fake DS responses left")
        return FakeHTTPResponse(queue.pop(0))

    return fake_urlopen


def write_demo_outputs(temp_state_dir: Path, compare_payload: dict[str, object], demo_dir: Path) -> None:
    demo_state_dir = demo_dir / "state"
    demo_state_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        "universe_all.json",
        "universe_filtered.json",
        "universe_top120.json",
        "universe_top30.json",
        "universe_runs.jsonl",
    ):
        shutil.copyfile(temp_state_dir / filename, demo_state_dir / filename)
    source_strategies = temp_state_dir / "strategies"
    if source_strategies.exists():
        shutil.copytree(source_strategies, demo_state_dir / "strategies", dirs_exist_ok=True)
    demo_compare = json.loads(json.dumps(compare_payload))
    for row in demo_compare.get("strategies", []):
        if isinstance(row, dict) and row.get("strategy"):
            row["state_dir"] = str((demo_state_dir / "strategies" / str(row["strategy"])).resolve())
    (demo_dir / "strategy_compare.json").write_text(
        json.dumps(demo_compare, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-demo", action="store_true")
    parser.add_argument("--demo-dir", default=str(ROOT / "demo"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        state_dir = tmp / "state"
        report_log = tmp / "reports-log.jsonl"

        code, _, stderr = run_cli(["--state-dir", str(state_dir), "init", "--seed-file", str(ROOT / "seeds/initial_state.json")])
        assert code == 0, stderr

        start_time = datetime(2026, 3, 11, 9, 0, tzinfo=timezone(timedelta(hours=8)))
        for step in range(6):
            run_time = (start_time + timedelta(minutes=15 * step)).isoformat(timespec="seconds")
            with patch("sim_trading.universe.urlopen", new=fake_universe_urlopen(run_time, step)):
                code, stdout, stderr = run_cli(
                    [
                        "--state-dir",
                        str(state_dir),
                        "--report-log",
                        str(report_log),
                        "universe-refresh",
                        "--timestamp",
                        run_time,
                    ]
                )
            assert code == 0, stderr
            assert "top120=120" in stdout

        universe_all = read_json(state_dir / "universe_all.json")
        universe_filtered = read_json(state_dir / "universe_filtered.json")
        universe_top120 = read_json(state_dir / "universe_top120.json")
        universe_top30 = read_json(state_dir / "universe_top30.json")
        assert universe_all["count"] == 136
        assert universe_filtered["count"] == 132
        assert universe_top120["count"] == 120
        assert universe_top30["count"] == 30
        excluded_symbols = {
            item["symbol"]: set(item["excluded_reasons"])
            for item in universe_all["items"]
            if item["symbol"] in {"BTCUP/USDT", "USDC/USDT", "NEWCOIN/USDT", "WIDESPREAD/USDT"}
        }
        assert "leveraged_token" in excluded_symbols["BTCUP/USDT"]
        assert "stable_stable" in excluded_symbols["USDC/USDT"]
        assert "listing_age_lt_60d" in excluded_symbols["NEWCOIN/USDT"]
        assert "spread_gt_0_30pct" in excluded_symbols["WIDESPREAD/USDT"]

        code, stdout, stderr = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "--report-log",
                str(report_log),
                "strategy-run",
                "--strategy",
                "baseline",
                "--timestamp",
                (start_time + timedelta(minutes=90)).isoformat(timespec="seconds"),
            ]
        )
        assert code == 0, stderr
        assert "execution_id=" in stdout

        top30_symbols = universe_top30["symbols"]
        ds_env = {
            "SIM_TRADING_DEEPSEEK_ENABLED": "1",
            "SIM_TRADING_DEEPSEEK_API_KEY": "verification-ds-key",
            "SIM_TRADING_DEEPSEEK_MODEL": "deepseek-chat",
        }
        with patch.dict(os.environ, ds_env, clear=False), patch(
            "sim_trading.ds_operator.urlopen",
            new=fake_ds_urlopen_factory([build_ds_plan(top30_symbols, aggressive=False)]),
        ):
            code, stdout, stderr = run_cli(
                [
                    "--state-dir",
                    str(state_dir),
                    "--report-log",
                    str(report_log),
                    "strategy-run",
                    "--strategy",
                    "ds_conservative",
                    "--timestamp",
                    (start_time + timedelta(minutes=120)).isoformat(timespec="seconds"),
                ]
            )
        assert code == 0, stderr
        assert "decision_id=" in stdout

        with patch.dict(os.environ, ds_env, clear=False), patch(
            "sim_trading.ds_operator.urlopen",
            new=fake_ds_urlopen_factory([build_ds_plan(top30_symbols, aggressive=True)]),
        ):
            code, stdout, stderr = run_cli(
                [
                    "--state-dir",
                    str(state_dir),
                    "--report-log",
                    str(report_log),
                    "strategy-run",
                    "--strategy",
                    "ds_aggressive",
                    "--timestamp",
                    (start_time + timedelta(minutes=150)).isoformat(timespec="seconds"),
                ]
            )
        assert code == 0, stderr
        assert "decision_id=" in stdout

        baseline_trades = read_csv_rows(state_dir / "strategies" / "baseline" / "trades.csv")
        conservative_trades = read_csv_rows(state_dir / "strategies" / "ds_conservative" / "trades.csv")
        aggressive_trades = read_csv_rows(state_dir / "strategies" / "ds_aggressive" / "trades.csv")
        root_trades = read_csv_rows(state_dir / "trades.csv")
        assert len(root_trades) == 0
        assert len(baseline_trades) > 0
        assert len(conservative_trades) > 0
        assert len(aggressive_trades) > 0
        assert baseline_trades != conservative_trades

        code, stdout, stderr = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "strategy-compare",
                "--output-json",
                "--timestamp",
                (start_time + timedelta(minutes=165)).isoformat(timespec="seconds"),
            ]
        )
        assert code == 0, stderr
        compare_payload = json.loads(stdout)
        strategies = {row["strategy"]: row for row in compare_payload["strategies"]}
        assert set(strategies) == {"baseline", "ds_conservative", "ds_aggressive"}
        assert "turnover_ratio" in strategies["baseline"]
        assert "risk_trigger_count" in strategies["ds_conservative"]

        handler = make_dashboard_handler(
            DashboardServerConfig(
                state_dir=state_dir,
                report_log=report_log,
                notification_limit=5,
            )
        )
        _, body = roundtrip(handler, http_request("GET", "/api/status?n=5"))
        payload = json.loads(body.decode("utf-8"))
        assert payload["snapshot"]["universe_status"]["top120_count"] == 120
        assert len(payload["snapshot"]["strategy_compare"]["strategies"]) == 3
        assert payload["universe_status"]["top30_count"] == 30
        assert len(payload["strategy_compare"]["strategies"]) == 3
        assert [tab["id"] for tab in payload["strategy_tabs"]] == ["overview", "baseline", "ds_conservative", "ds_aggressive"]

        _, body = roundtrip(handler, http_request("GET", "/api/strategy?name=ds_conservative"))
        strategy_payload = json.loads(body.decode("utf-8"))
        assert strategy_payload["strategy"]["strategy"] == "ds_conservative"
        assert strategy_payload["strategy"]["profile"]["uses_ds"] is True
        assert strategy_payload["strategy"]["summary"]["nav"] is not None
        assert "recent_trades" in strategy_payload["strategy"]
        assert "recent_events" in strategy_payload["strategy"]

        if args.write_demo:
            write_demo_outputs(state_dir, compare_payload, Path(args.demo_dir))

    print("universe-filter-outputs: ok")
    print("strategy-state-isolation: ok")
    print("strategy-compare-output: ok")
    print("dashboard-api-universe-compare: ok")
    print("strategy-detail-api: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
