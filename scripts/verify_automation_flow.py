from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim_trading.cli import main as cli_main
from sim_trading.ops import build_status_snapshot
from sim_trading.storage import read_jsonl


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, str]) -> None:
        self.payload = payload
        self.status = 200

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def fake_urlopen_factory(quotes: dict[str, str]):
    def fake_urlopen(request, timeout=10):  # noqa: ANN001
        full_url = request.full_url if hasattr(request, "full_url") else str(request)
        symbol = full_url.split("symbol=", 1)[1]
        if symbol not in quotes:
            raise RuntimeError(f"unknown symbol {symbol}")
        return FakeHTTPResponse({"symbol": symbol, "price": quotes[symbol]})

    return fake_urlopen


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli_main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        state_dir = tmp / "state"
        report_log = tmp / "reports-log.jsonl"
        ops_env = tmp / ".ops.env"

        code, _, _ = run_cli(["--state-dir", str(state_dir), "init", "--seed-file", str(ROOT / "seeds/initial_state.json")])
        assert code == 0

        snapshots = [
            ("2026-03-11T09:00:00+08:00", {"BTCUSDT": "40.0", "DOTUSDT": "7.0", "LINKUSDT": "18.0"}),
            ("2026-03-11T10:00:00+08:00", {"BTCUSDT": "41.2", "DOTUSDT": "6.9", "LINKUSDT": "17.8"}),
            ("2026-03-11T11:00:00+08:00", {"BTCUSDT": "42.5", "DOTUSDT": "6.8", "LINKUSDT": "17.6"}),
            ("2026-03-11T12:00:00+08:00", {"BTCUSDT": "44.0", "DOTUSDT": "6.7", "LINKUSDT": "17.4"}),
            ("2026-03-11T13:00:00+08:00", {"BTCUSDT": "43.0", "DOTUSDT": "6.8", "LINKUSDT": "17.7"}),
            ("2026-03-11T14:00:00+08:00", {"BTCUSDT": "42.0", "DOTUSDT": "6.95", "LINKUSDT": "18.1"}),
            ("2026-03-11T15:00:00+08:00", {"BTCUSDT": "41.0", "DOTUSDT": "7.1", "LINKUSDT": "18.6"}),
            ("2026-03-11T16:00:00+08:00", {"BTCUSDT": "40.5", "DOTUSDT": "7.25", "LINKUSDT": "19.0"}),
            ("2026-03-11T17:00:00+08:00", {"BTCUSDT": "40.2", "DOTUSDT": "7.4", "LINKUSDT": "19.4"}),
            ("2026-03-11T18:00:00+08:00", {"BTCUSDT": "39.8", "DOTUSDT": "7.6", "LINKUSDT": "19.8"}),
        ]
        for timestamp, quotes in snapshots:
            with patch("sim_trading.market.urlopen", new=fake_urlopen_factory(quotes)):
                code, stdout, _ = run_cli(
                    [
                        "--state-dir",
                        str(state_dir),
                        "fetch-market",
                        "--symbol",
                        "BTC/USDT",
                        "--symbol",
                        "DOT/USDT",
                        "--symbol",
                        "LINK/USDT",
                        "--api-root",
                        "https://api.binance.com",
                        "--timestamp",
                        timestamp,
                    ]
                )
            assert code == 0
            assert "BTC/USDT" in stdout

        code, stdout, _ = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "--report-log",
                str(report_log),
                "normalize-positions",
                "--timestamp",
                "2026-03-11T18:05:00+08:00",
            ]
        )
        assert code == 0
        assert "normalized_positions=3" in stdout
        assert (state_dir / "position_normalizations.jsonl").exists()

        code, stdout, _ = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "run-signals",
                "--report-log",
                str(report_log),
                "--lookback-points",
                "6",
                "--notify",
                "--timestamp",
                "2026-03-11T18:10:00+08:00",
            ]
        )
        assert code == 0
        assert "bullish" in stdout

        code, stdout, _ = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "--report-log",
                str(report_log),
                "execute-sim",
                "--lookback-points",
                "6",
                "--timestamp",
                "2026-03-11T18:15:00+08:00",
            ]
        )
        assert code == 0
        assert "status=" in stdout

        code, stdout, _ = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "risk-status",
                "--kill-switch",
                "on",
                "--reason",
                "verification kill switch",
                "--timestamp",
                "2026-03-11T19:00:00+08:00",
                "--output-json",
            ]
        )
        assert code == 0
        assert "kill_switch_toggled" in stdout

        code, stdout, _ = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "risk-check",
                "--timestamp",
                "2026-03-11T19:05:00+08:00",
            ]
        )
        assert code == 1
        assert "blocked_new_orders=True" in stdout

        code, stdout, _ = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "--report-log",
                str(report_log),
                "execute-sim",
                "--lookback-points",
                "6",
                "--timestamp",
                "2026-03-11T19:15:00+08:00",
                "--notify",
            ]
        )
        assert code == 0
        assert "risk-rejection" in stdout

        code, stdout, _ = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "risk-status",
                "--kill-switch",
                "off",
                "--reason",
                "verification clear",
                "--timestamp",
                "2026-03-11T19:20:00+08:00",
            ]
        )
        assert code == 0
        assert "Blocked New Orders: False" in stdout

        code, stdout, _ = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "--report-log",
                str(report_log),
                "validate-strategy",
                "--lookback-points",
                "4",
                "--step-points",
                "1",
                "--timestamp",
                "2026-03-11T20:00:00+08:00",
            ]
        )
        assert code == 0
        assert "profit_factor=" in stdout

        market_feed = read_jsonl(state_dir / "market_feed.jsonl")
        signal_runs = read_jsonl(state_dir / "signal_runs.jsonl")
        execution_runs = read_jsonl(state_dir / "execution_runs.jsonl")
        risk_events = read_jsonl(state_dir / "risk_events.jsonl")
        validation_runs = read_jsonl(state_dir / "validation_runs.jsonl")
        assert len(market_feed) == 10
        assert len(signal_runs) == 1
        assert len(execution_runs) == 2
        assert len(risk_events) >= 2
        assert len(validation_runs) == 1
        assert (state_dir / "risk_state.json").exists()
        assert (state_dir / "order_events.jsonl").exists()

        snapshot = build_status_snapshot(state_dir=state_dir)
        assert snapshot["latest_market_fetch_at"] == "2026-03-11T18:00:00+08:00"
        assert snapshot["latest_signal_summary"]
        assert snapshot["position_mode_is_normalized"] is True
        assert len(snapshot["timeseries"]["equity_curve"]) >= 1
        assert snapshot["latest_execution_summary"]
        assert snapshot["latest_validation_summary"]
        assert snapshot["risk_status"]["consecutive_loss_count"] >= 1

        code, stdout, _ = run_cli(["rotate-tokens", "--ops-env", str(ops_env)])
        assert code == 0
        ops_contents = ops_env.read_text(encoding="utf-8")
        assert "SIM_TRADING_WEBHOOK_TOKEN=" in ops_contents
        webhook_secret = next(
            line.split("=", 1)[1]
            for line in ops_contents.splitlines()
            if line.startswith("SIM_TRADING_WEBHOOK_TOKEN=")
        )
        assert webhook_secret not in stdout
        assert "..." in stdout

        run_dir = tmp / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "dashboard.pid").write_text(str(os.getpid()), encoding="utf-8")
        (run_dir / "webhook.pid").write_text(str(os.getpid()), encoding="utf-8")
        code, stdout, _ = run_cli(
            [
                "--state-dir",
                str(state_dir),
                "health-check",
                "--report-log",
                str(report_log),
                "--dashboard-pid-file",
                str(run_dir / "dashboard.pid"),
                "--webhook-pid-file",
                str(run_dir / "webhook.pid"),
                "--dashboard-health-url",
                "",
                "--webhook-host",
                "",
                "--webhook-port",
                "0",
                "--max-report-age-seconds",
                "86400",
            ]
        )
        assert code == 0
        assert "Health: ok" in stdout

        for script_name in [
            "scripts/cron_phase1.sh",
            "scripts/ops_start.sh",
            "scripts/ops_status.sh",
            "scripts/ops_restart.sh",
            "scripts/post_task_done.sh",
        ]:
            completed = subprocess.run(
                ["bash", "-n", str(ROOT / script_name)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr

        cron_text = (ROOT / "scripts/cron_phase1.sh").read_text(encoding="utf-8")
        assert "fetch-market" in cron_text
        assert "run-signals" in cron_text
        assert "ds-shadow-run" in cron_text
        assert "execute-sim" in cron_text
        assert "validate-strategy" in cron_text
        assert "RUN_DS_SHADOW" in cron_text
        assert "DS_SHADOW_EVERY_HOURS" in cron_text

    print("fetch-market-cli: ok")
    print("normalize-positions-cli: ok")
    print("run-signals-cli: ok")
    print("execute-sim-cli: ok")
    print("risk-status-cli: ok")
    print("validate-strategy-cli: ok")
    print("rotate-tokens: ok")
    print("health-check: ok")
    print("ops-scripts-syntax: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
