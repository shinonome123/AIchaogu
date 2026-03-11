from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim_trading.cli import main as cli_main
from sim_trading.ledger import LedgerService
from sim_trading.market import run_signal_snapshot
from sim_trading.storage import append_jsonl, read_jsonl


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.status = 200

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def fake_ds_urlopen_factory(responses: list[dict[str, object]]):
    queue = list(responses)

    def fake_urlopen(request, timeout=20):  # noqa: ANN001
        if not queue:
            raise RuntimeError("no fake DeepSeek responses left")
        payload = queue.pop(0)
        return FakeHTTPResponse(payload)

    return fake_urlopen


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli_main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def prepare_state(state_dir: Path) -> None:
    service = LedgerService(state_dir)
    service.initialize_from_seed(ROOT / "seeds/initial_state.json")
    feed_rows = [
        (
            "2026-03-11T09:00:00+08:00",
            {"BTC/USDT": "40.0", "DOT/USDT": "7.0", "LINK/USDT": "18.0"},
        ),
        (
            "2026-03-11T10:00:00+08:00",
            {"BTC/USDT": "41.2", "DOT/USDT": "6.9", "LINK/USDT": "17.8"},
        ),
        (
            "2026-03-11T11:00:00+08:00",
            {"BTC/USDT": "42.5", "DOT/USDT": "6.8", "LINK/USDT": "17.6"},
        ),
        (
            "2026-03-11T12:00:00+08:00",
            {"BTC/USDT": "44.0", "DOT/USDT": "6.7", "LINK/USDT": "17.4"},
        ),
        (
            "2026-03-11T13:00:00+08:00",
            {"BTC/USDT": "43.0", "DOT/USDT": "6.8", "LINK/USDT": "17.7"},
        ),
        (
            "2026-03-11T14:00:00+08:00",
            {"BTC/USDT": "42.0", "DOT/USDT": "6.95", "LINK/USDT": "18.1"},
        ),
        (
            "2026-03-11T15:00:00+08:00",
            {"BTC/USDT": "41.0", "DOT/USDT": "7.1", "LINK/USDT": "18.6"},
        ),
        (
            "2026-03-11T16:00:00+08:00",
            {"BTC/USDT": "40.5", "DOT/USDT": "7.25", "LINK/USDT": "19.0"},
        ),
        (
            "2026-03-11T17:00:00+08:00",
            {"BTC/USDT": "40.2", "DOT/USDT": "7.4", "LINK/USDT": "19.4"},
        ),
        (
            "2026-03-11T18:00:00+08:00",
            {"BTC/USDT": "39.8", "DOT/USDT": "7.6", "LINK/USDT": "19.8"},
        ),
    ]
    latest_prices: dict[str, dict[str, str]] = {}
    for timestamp, prices in feed_rows:
        append_jsonl(
            service.paths.market_feed,
            {
                "timestamp": timestamp,
                "source": "verification",
                "symbols": list(prices),
                "prices": {
                    symbol: {
                        "symbol": symbol,
                        "price": price,
                        "timestamp": timestamp,
                        "source": "verification",
                    }
                    for symbol, price in prices.items()
                },
            },
        )
        latest_prices = {
            symbol: {
                "price": price,
                "timestamp": timestamp,
            }
            for symbol, price in prices.items()
        }
    service.save_market_prices(latest_prices)
    service.normalize_seed_positions(
        timestamp="2026-03-11T18:05:00+08:00",
        source_note="Verification normalized legacy synthetic seed units.",
    )
    run_signal_snapshot(
        state_dir=state_dir,
        source="verification",
        lookback_points=6,
        timestamp="2026-03-11T18:10:00+08:00",
    )


def main() -> int:
    valid_plan = {
        "id": "resp-valid",
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "market_regime": "trending",
                            "global_risk_mode": "normal",
                            "decisions": [
                                {
                                    "symbol": "BTC/USDT",
                                    "action": "hold",
                                    "target_weight": 0.33,
                                    "confidence": 0.67,
                                    "entry_reason": "Preserve the core position while trend confirmation is mixed.",
                                    "invalidation": "Break below the current support and lose the trend signal.",
                                    "stop_loss_pct": 0.05,
                                    "take_profit_pct": 0.12,
                                },
                                {
                                    "symbol": "DOT/USDT",
                                    "action": "buy",
                                    "target_weight": 0.35,
                                    "confidence": 0.74,
                                    "entry_reason": "Momentum and signal snapshot both favor a slightly larger allocation.",
                                    "invalidation": "Momentum rolls over and the signal turns bearish.",
                                    "stop_loss_pct": 0.04,
                                    "take_profit_pct": 0.10,
                                },
                                {
                                    "symbol": "LINK/USDT",
                                    "action": "sell",
                                    "target_weight": 0.0,
                                    "confidence": 0.71,
                                    "entry_reason": "Relative strength has weakened versus the other tracked names.",
                                    "invalidation": "Relative strength returns and the symbol regains leadership.",
                                    "stop_loss_pct": 0.05,
                                    "take_profit_pct": 0.08,
                                },
                            ],
                        }
                    )
                }
            }
        ],
    }
    invalid_plan = {
        "id": "resp-invalid",
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "market_regime": "trending",
                            "global_risk_mode": "normal",
                            "decisions": [
                                {
                                    "symbol": "DOGE/USDT",
                                    "action": "buy",
                                    "target_weight": 0.2,
                                    "confidence": 0.6,
                                    "entry_reason": "Unknown symbol for this state.",
                                    "invalidation": "Context never included this symbol.",
                                    "stop_loss_pct": 0.05,
                                    "take_profit_pct": 0.1,
                                }
                            ],
                        }
                    )
                }
            }
        ],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        state_dir = tmp / "state"
        report_log = tmp / "reports-log.jsonl"
        prepare_state(state_dir)

        env = {
            "SIM_TRADING_DEEPSEEK_ENABLED": "1",
            "SIM_TRADING_DEEPSEEK_API_KEY": "test-deepseek-key",
            "SIM_TRADING_DEEPSEEK_MODEL": "deepseek-chat",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("sim_trading.ds_operator.urlopen", new=fake_ds_urlopen_factory([valid_plan])):
                code, stdout, stderr = run_cli(
                    [
                        "--state-dir",
                        str(state_dir),
                        "--report-log",
                        str(report_log),
                        "ds-shadow-run",
                        "--timestamp",
                        "2026-03-11T18:12:00+08:00",
                    ]
                )
            assert code == 0, stderr
            assert "regime=trending" in stdout
            assert "DOT/USDT action=buy" in stdout

            code, stdout, stderr = run_cli(
                [
                    "--state-dir",
                    str(state_dir),
                    "--report-log",
                    str(report_log),
                    "ds-approve-latest",
                    "--timestamp",
                    "2026-03-11T18:13:00+08:00",
                ]
            )
            assert code == 0, stderr
            assert "approval_id=" in stdout

            code, stdout, stderr = run_cli(
                [
                    "--state-dir",
                    str(state_dir),
                    "--report-log",
                    str(report_log),
                    "execute-sim",
                    "--decision-source",
                    "ds-approved",
                    "--timestamp",
                    "2026-03-11T18:15:00+08:00",
                ]
            )
            assert code == 0, stderr
            assert "status=" in stdout

            with patch("sim_trading.ds_operator.urlopen", new=fake_ds_urlopen_factory([invalid_plan])):
                code, stdout, stderr = run_cli(
                    [
                        "--state-dir",
                        str(state_dir),
                        "--report-log",
                        str(report_log),
                        "ds-shadow-run",
                        "--timestamp",
                        "2026-03-11T18:16:00+08:00",
                    ]
                )
            assert code == 1
            assert "reason=" in stdout

        ds_requests = read_jsonl(state_dir / "ds_requests.jsonl")
        ds_decisions = read_jsonl(state_dir / "ds_decisions.jsonl")
        ds_rejections = read_jsonl(state_dir / "ds_rejections.jsonl")
        ds_approvals = read_jsonl(state_dir / "ds_approvals.jsonl")
        execution_runs = read_jsonl(state_dir / "execution_runs.jsonl")

        assert len(ds_requests) == 2
        assert len(ds_decisions) == 1
        assert len(ds_rejections) >= 1
        assert len(ds_approvals) == 2
        assert ds_approvals[0]["status"] == "approved"
        assert ds_approvals[1]["status"] == "consumed"
        assert execution_runs[-1]["decision_source"] == "ds-approved"
        assert execution_runs[-1]["decision_id"] == ds_decisions[0]["decision_id"]
        assert "execution_preview" in ds_decisions[0]
        assert ds_requests[0]["messages"]
        assert ds_rejections[-1]["reason"]

    print("ds-schema-validation: ok")
    print("ds-shadow-approval-cycle: ok")
    print("ds-audit-logs: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
