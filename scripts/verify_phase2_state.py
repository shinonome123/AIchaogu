from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim_trading.cli import main as cli_main
from sim_trading.storage import read_json, read_jsonl


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

        dataset = [
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

        code, _, _ = run_cli(["--state-dir", str(state_dir), "init", "--seed-file", str(ROOT / "seeds/initial_state.json")])
        assert code == 0

        for timestamp, quotes in dataset:
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
                        "--timestamp",
                        timestamp,
                    ]
                )
            assert code == 0
            assert "source=binance" in stdout

        assert run_cli(
            [
                "--state-dir",
                str(state_dir),
                "--report-log",
                str(report_log),
                "normalize-positions",
                "--timestamp",
                "2026-03-11T18:05:00+08:00",
            ]
        )[0] == 0
        assert run_cli(
            [
                "--state-dir",
                str(state_dir),
                "--report-log",
                str(report_log),
                "run-signals",
                "--lookback-points",
                "6",
                "--timestamp",
                "2026-03-11T18:10:00+08:00",
            ]
        )[0] == 0
        assert run_cli(
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
        )[0] == 0
        assert run_cli(
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
            ]
        )[0] == 0
        assert run_cli(
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
        )[0] == 0
        assert run_cli(
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
        )[0] == 0
        assert run_cli(
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
        )[0] == 0

        risk_state = read_json(state_dir / "risk_state.json")
        order_events = read_jsonl(state_dir / "order_events.jsonl")
        execution_runs = read_jsonl(state_dir / "execution_runs.jsonl")
        risk_events = read_jsonl(state_dir / "risk_events.jsonl")
        validation_runs = read_jsonl(state_dir / "validation_runs.jsonl")

        statuses = {row["status"] for row in order_events if isinstance(row, dict) and "status" in row}
        assert {"pending", "partial", "filled", "rejected"}.issubset(statuses)
        assert risk_state["kill_switch_enabled"] is False
        assert risk_state["consecutive_loss_count"] >= 1
        assert len(execution_runs) == 2
        assert any(row.get("type") == "kill_switch_toggled" for row in risk_events if isinstance(row, dict))
        assert any(row.get("type") == "order_rejected_risk_gate" for row in risk_events if isinstance(row, dict))
        assert validation_runs[-1]["closed_trade_count"] >= 1
        assert "return_pct" in validation_runs[-1]
        assert "max_drawdown_pct" in validation_runs[-1]
        assert "profit_factor" in validation_runs[-1]

    print("phase2-order-lifecycle: ok")
    print("phase2-risk-events: ok")
    print("phase2-validation-metrics: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
