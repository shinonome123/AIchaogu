from __future__ import annotations

import base64
import json
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim_trading.ds_operator import build_signal_entry_from_ds_decision
from sim_trading.ledger import LedgerService
from sim_trading.execution import SimulationExecutor, set_kill_switch
from sim_trading.market import run_signal_snapshot
from sim_trading.notifier import notify_task
from sim_trading.security import DashboardAuthConfig
from sim_trading.servers import DashboardServerConfig, make_dashboard_handler
from sim_trading.storage import append_jsonl, read_jsonl
from sim_trading.strategy_tracks import ensure_strategy_state, sync_shared_market_data
from sim_trading.validation import StrategyValidator


class DummyServer:
    server_name = "localhost"
    server_port = 0


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


def http_request(method: str, path: str, headers: dict[str, str] | None = None) -> bytes:
    lines = [f"{method} {path} HTTP/1.0", "Host: localhost", "Connection: close"]
    for key, value in (headers or {}).items():
        lines.append(f"{key}: {value}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


def bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def basic(username: str, password: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def prepare_state(state_dir: Path, report_log: Path) -> None:
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
    executor = SimulationExecutor(state_dir)
    executor.execute_cycle(
        timestamp="2026-03-11T18:15:00+08:00",
        source="verification.execute",
        lookback_points=6,
    )
    set_kill_switch(
        state_dir,
        enabled=True,
        reason="verification kill switch",
        timestamp="2026-03-11T19:00:00+08:00",
    )
    executor.execute_cycle(
        timestamp="2026-03-11T19:15:00+08:00",
        source="verification.execute",
        lookback_points=6,
    )
    set_kill_switch(
        state_dir,
        enabled=False,
        reason="verification clear",
        timestamp="2026-03-11T19:20:00+08:00",
    )
    StrategyValidator(state_dir).validate(
        timestamp="2026-03-11T20:00:00+08:00",
        source="verification.validate",
        lookback_points=4,
        step_points=1,
    )
    notify_task(
        report_log=report_log,
        task="verification",
        status="ok",
        did_what="Prepared Phase2 dashboard payload with execution, risk, and validation data.",
        risk_impact="Simulation-only verification state including hard-risk rejection coverage.",
        next_step="Inspect API payload and HTML shell.",
        source="verification.dashboard",
        timestamp="2026-03-11T20:05:00+08:00",
    )
    append_jsonl(
        service.paths.ds_requests,
        {
            "request_id": "DSR-VERIFY000001",
            "timestamp": "2026-03-11T20:10:00+08:00",
            "source": "verification.ds",
            "provider": "deepseek",
            "enabled": True,
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "messages": [{"role": "system", "content": "verification"}],
            "context_meta": {"tracked_symbol_count": 3},
        },
    )
    append_jsonl(
        service.paths.ds_decisions,
        {
            "decision_id": "DSD-VERIFY000001",
            "request_id": "DSR-VERIFY000001",
            "timestamp": "2026-03-11T20:10:01+08:00",
            "source": "verification.ds",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "status": "validated",
            "summary": "regime=trending risk=normal buy=1 sell=1 hold=1",
            "market_regime": "trending",
            "global_risk_mode": "normal",
            "market_timestamp": "2026-03-11T18:00:00+08:00",
            "signal_timestamp": "2026-03-11T18:10:00+08:00",
            "decision_count": 3,
            "payload": {
                "market_regime": "trending",
                "global_risk_mode": "normal",
                "decisions": [
                    {
                        "symbol": "BTC/USDT",
                        "action": "hold",
                        "target_weight": "0.33",
                        "confidence": "0.65",
                        "entry_reason": "Keep the existing position.",
                        "invalidation": "Trend breaks down.",
                        "stop_loss_pct": "0.05",
                        "take_profit_pct": "0.12",
                    },
                    {
                        "symbol": "DOT/USDT",
                        "action": "buy",
                        "target_weight": "0.35",
                        "confidence": "0.74",
                        "entry_reason": "Momentum remains constructive.",
                        "invalidation": "Momentum rolls over.",
                        "stop_loss_pct": "0.04",
                        "take_profit_pct": "0.10",
                    },
                    {
                        "symbol": "LINK/USDT",
                        "action": "sell",
                        "target_weight": "0",
                        "confidence": "0.70",
                        "entry_reason": "Relative strength is weaker.",
                        "invalidation": "Leadership returns.",
                        "stop_loss_pct": "0.05",
                        "take_profit_pct": "0.08",
                    },
                ],
            },
            "execution_preview": {
                "timestamp": "2026-03-11T20:10:01+08:00",
                "targets": [
                    {
                        "symbol": "BTC/USDT",
                        "target_weight": "0.33",
                        "action": "hold",
                        "confidence": "0.65",
                        "rationale": "verification",
                        "stop_loss_pct": "0.05",
                        "take_profit_pct": "0.12",
                    },
                    {
                        "symbol": "DOT/USDT",
                        "target_weight": "0.35",
                        "action": "buy",
                        "confidence": "0.74",
                        "rationale": "verification",
                        "stop_loss_pct": "0.04",
                        "take_profit_pct": "0.10",
                    },
                ],
                "signals": [],
                "adjustments": [],
            },
        },
    )
    append_jsonl(
        service.paths.ds_rejections,
        {
            "rejection_id": "DSX-VERIFY000001",
            "timestamp": "2026-03-11T20:11:00+08:00",
            "source": "verification.ds",
            "status": "rejected",
            "reason": "decision symbol is outside current market universe: DOGE/USDT",
            "summary": "decision symbol is outside current market universe: DOGE/USDT",
        },
    )
    append_jsonl(
        service.paths.ds_approvals,
        {
            "approval_id": "DSA-VERIFY000001",
            "timestamp": "2026-03-11T20:12:00+08:00",
            "source": "verification.ds",
            "status": "approved",
            "decision_id": "DSD-VERIFY000001",
            "decision_timestamp": "2026-03-11T20:10:01+08:00",
            "decision_summary": "regime=trending risk=normal buy=1 sell=1 hold=1",
        },
    )

    prepare_strategy_track(state_dir, strategy="baseline", timestamp="2026-03-11T20:20:00+08:00")
    prepare_strategy_track(state_dir, strategy="ds_conservative", timestamp="2026-03-11T20:30:00+08:00")
    prepare_strategy_track(state_dir, strategy="ds_aggressive", timestamp="2026-03-11T20:40:00+08:00")


def prepare_strategy_track(state_dir: Path, *, strategy: str, timestamp: str) -> None:
    symbols = ["BTC/USDT", "DOT/USDT", "LINK/USDT"]
    strategy_service = ensure_strategy_state(state_dir, strategy=strategy, timestamp=timestamp, symbols=symbols)
    strategy_dir = sync_shared_market_data(state_dir, strategy=strategy)
    strategy_service = LedgerService(strategy_dir)

    if strategy == "baseline":
        signal_entry = run_signal_snapshot(
            state_dir=strategy_dir,
            source=f"verification.{strategy}.signals",
            lookback_points=6,
            timestamp=timestamp,
        ).entry
        SimulationExecutor(strategy_dir).execute_cycle(
            timestamp=timestamp,
            signal_run_entry=signal_entry,
            source=f"verification.{strategy}.execute",
            lookback_points=6,
        )
    else:
        request_id = f"DSR-{strategy.upper()}-VERIFY"
        decision_id = f"DSD-{strategy.upper()}-VERIFY"
        append_jsonl(
            strategy_service.paths.ds_requests,
            {
                "request_id": request_id,
                "timestamp": timestamp,
                "source": f"verification.{strategy}.ds",
                "provider": "deepseek",
                "enabled": True,
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com",
                "messages": [{"role": "system", "content": "verification"}],
                "context_meta": {"tracked_symbol_count": len(symbols)},
            },
        )
        decision_entry = {
            "decision_id": decision_id,
            "request_id": request_id,
            "timestamp": timestamp,
            "source": f"verification.{strategy}.ds",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "status": "validated",
            "summary": "regime=trending risk=normal buy=1 sell=1 hold=1",
            "market_regime": "trending",
            "global_risk_mode": "normal" if strategy == "ds_aggressive" else "cautious",
            "market_timestamp": "2026-03-11T18:00:00+08:00",
            "signal_timestamp": timestamp,
            "decision_count": 3,
            "payload": {
                "market_regime": "trending",
                "global_risk_mode": "normal" if strategy == "ds_aggressive" else "cautious",
                "decisions": [
                    {
                        "symbol": "BTC/USDT",
                        "action": "buy",
                        "target_weight": "0.08",
                        "confidence": "0.72",
                        "entry_reason": "BTC trend remains constructive.",
                        "invalidation": "BTC loses short-term support.",
                        "stop_loss_pct": "0.04",
                        "take_profit_pct": "0.08",
                    },
                    {
                        "symbol": "DOT/USDT",
                        "action": "buy",
                        "target_weight": "0.08",
                        "confidence": "0.68",
                        "entry_reason": "DOT relative strength has improved.",
                        "invalidation": "DOT breaks relative support.",
                        "stop_loss_pct": "0.04",
                        "take_profit_pct": "0.08",
                    },
                    {
                        "symbol": "LINK/USDT",
                        "action": "hold",
                        "target_weight": "0.05",
                        "confidence": "0.60",
                        "entry_reason": "LINK is stable but not accelerating.",
                        "invalidation": "LINK momentum flips negative.",
                        "stop_loss_pct": "0.05",
                        "take_profit_pct": "0.07",
                    },
                ],
            },
            "execution_preview": {
                "timestamp": timestamp,
                "targets": [],
                "signals": [],
                "adjustments": [],
            },
        }
        append_jsonl(strategy_service.paths.ds_decisions, decision_entry)
        if strategy == "ds_conservative":
            append_jsonl(
                strategy_service.paths.ds_approvals,
                {
                    "approval_id": "DSA-DS_CONSERVATIVE-VERIFY",
                    "timestamp": "2026-03-11T20:31:00+08:00",
                    "source": "verification.ds_conservative.ds",
                    "status": "approved",
                    "decision_id": decision_id,
                    "decision_timestamp": timestamp,
                    "decision_summary": "regime=trending risk=cautious buy=2 sell=0 hold=1",
                },
            )
        else:
            append_jsonl(
                strategy_service.paths.ds_rejections,
                {
                    "rejection_id": "DSX-DS_AGGRESSIVE-VERIFY",
                    "timestamp": "2026-03-11T20:41:00+08:00",
                    "source": "verification.ds_aggressive.ds",
                    "status": "rejected",
                    "reason": "risk gate required smaller target weight for BTC/USDT",
                    "summary": "risk gate required smaller target weight for BTC/USDT",
                },
            )
        signal_entry = build_signal_entry_from_ds_decision(
            state_dir=strategy_dir,
            decision_entry=decision_entry,
            source=f"verification.{strategy}.decision",
            timestamp=timestamp,
        )
        SimulationExecutor(strategy_dir).execute_cycle(
            timestamp=timestamp,
            signal_run_entry=signal_entry,
            source=f"verification.{strategy}.execute",
            lookback_points=6,
        )
        if strategy == "ds_aggressive":
            set_kill_switch(
                strategy_dir,
                enabled=True,
                reason="verification aggressive block",
                timestamp="2026-03-11T20:42:00+08:00",
            )
            SimulationExecutor(strategy_dir).execute_cycle(
                timestamp="2026-03-11T20:43:00+08:00",
                signal_run_entry=signal_entry,
                source="verification.ds_aggressive.execute",
                lookback_points=6,
            )
            set_kill_switch(
                strategy_dir,
                enabled=False,
                reason="verification aggressive clear",
                timestamp="2026-03-11T20:44:00+08:00",
            )

    StrategyValidator(strategy_dir).validate(
        timestamp="2026-03-11T20:45:00+08:00",
        source=f"verification.{strategy}.validate",
        lookback_points=4,
        step_points=1,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        state_dir = tmp / "state"
        report_log = tmp / "reports-log.jsonl"
        prepare_state(state_dir, report_log)
        os.environ["SIM_TRADING_DEEPSEEK_ENABLED"] = "1"
        os.environ["SIM_TRADING_DEEPSEEK_API_KEY"] = "verification-key"

        audit_rows = read_jsonl(state_dir / "position_normalizations.jsonl")
        assert len(audit_rows) == 1
        assert audit_rows[0]["mode_after"] == "normalized_seed_notional"
        assert len(read_jsonl(state_dir / "execution_runs.jsonl")) == 2
        assert len(read_jsonl(state_dir / "validation_runs.jsonl")) == 1
        assert len(read_jsonl(state_dir / "risk_events.jsonl")) >= 2
        assert len(read_jsonl(state_dir / "ds_decisions.jsonl")) == 1
        assert len(read_jsonl(state_dir / "ds_rejections.jsonl")) == 1
        assert len(read_jsonl(state_dir / "ds_approvals.jsonl")) == 1

        handler = make_dashboard_handler(
            DashboardServerConfig(
                state_dir=state_dir.resolve(),
                report_log=report_log.resolve(),
                notification_limit=2,
                auth=DashboardAuthConfig(
                    bearer_token="dash-token",
                    basic_username="ops",
                    basic_password="dash-pass",
                ),
            )
        )

        head, body = roundtrip(handler, http_request("GET", "/api/status?n=2", headers=bearer("dash-token")))
        assert b"200" in head.split(b"\r\n", 1)[0]
        payload = json.loads(body.decode("utf-8"))
        snapshot = payload["snapshot"]
        assert snapshot["position_mode"] == "normalized_seed_notional"
        assert snapshot["position_mode_is_normalized"] is True
        assert snapshot["position_requires_normalization"] is False
        assert snapshot["position_normalized_at"] == "2026-03-11T18:05:00+08:00"
        assert len(snapshot["timeseries"]["equity_curve"]) >= 2
        assert set(snapshot["timeseries"]["market_prices"]) == {"DOT/USDT", "LINK/USDT"}
        assert len(snapshot["timeseries"]["market_prices"]["LINK/USDT"]) == 10
        assert snapshot["timeseries"]["equity_curve"][-1]["nav"] == snapshot["nav"]
        assert snapshot["latest_execution_run"]["rejected_orders"] >= 1
        assert snapshot["risk_status"]["consecutive_loss_count"] >= 1
        assert snapshot["latest_validation_run"]["closed_trade_count"] >= 1
        assert snapshot["ds_mode"] == "approval"
        assert snapshot["latest_ds_decision"]["decision_id"] == "DSD-VERIFY000001"
        assert snapshot["latest_ds_decision_summary"] == "regime=trending risk=normal buy=1 sell=1 hold=1"
        assert snapshot["latest_ds_rejection"]["reason"].startswith("decision symbol is outside")
        assert snapshot["latest_ds_approval_summary"] == "approved DSD-VERIFY000001"
        assert payload["latest_ds_decision"]["decision_id"] == "DSD-VERIFY000001"
        assert payload["latest_ds_rejection"]["rejection_id"] == "DSX-VERIFY000001"
        assert payload["latest_ds_approval"]["approval_id"] == "DSA-VERIFY000001"
        assert payload["ds_mode"] == "approval"
        assert payload["default_strategy_view"] == "overview"
        assert [tab["id"] for tab in payload["strategy_tabs"]] == ["overview", "baseline", "ds_conservative", "ds_aggressive"]
        assert payload["strategy_tabs"][1]["initialized"] is True
        assert len(payload["latest_notifications"]) <= 2

        head, body = roundtrip(handler, http_request("GET", "/api/status?n=1", headers=basic("ops", "dash-pass")))
        assert b"200" in head.split(b"\r\n", 1)[0]

        head, body = roundtrip(
            handler,
            http_request("GET", "/api/strategy?name=baseline", headers=bearer("dash-token")),
        )
        assert b"200" in head.split(b"\r\n", 1)[0]
        baseline_payload = json.loads(body.decode("utf-8"))
        baseline_strategy = baseline_payload["strategy"]
        assert baseline_strategy["strategy"] == "baseline"
        assert baseline_strategy["initialized"] is True
        assert baseline_strategy["profile"]["uses_ds"] is False
        assert baseline_strategy["summary"]["nav"] is not None
        assert "gross_exposure_pct" in baseline_strategy["positions_summary"]
        assert isinstance(baseline_strategy["recent_trades"], list)
        assert baseline_strategy["latest_execution_run"] is not None

        head, body = roundtrip(
            handler,
            http_request("GET", "/api/strategy?name=ds_conservative", headers=bearer("dash-token")),
        )
        assert b"200" in head.split(b"\r\n", 1)[0]
        ds_payload = json.loads(body.decode("utf-8"))
        ds_strategy = ds_payload["strategy"]
        assert ds_strategy["strategy"] == "ds_conservative"
        assert ds_strategy["profile"]["uses_ds"] is True
        assert ds_strategy["latest_ds_decision"]["decision_id"] == "DSD-DS_CONSERVATIVE-VERIFY"
        assert ds_strategy["latest_ds_approval"]["approval_id"] == "DSA-DS_CONSERVATIVE-VERIFY"
        assert isinstance(ds_strategy["recent_events"], list)
        assert ds_strategy["summary"]["risk_trigger_count"] >= 0

        head, body = roundtrip(
            handler,
            http_request("GET", "/api/strategy?name=ds_aggressive", headers=bearer("dash-token")),
        )
        assert b"200" in head.split(b"\r\n", 1)[0]
        aggressive_payload = json.loads(body.decode("utf-8"))
        aggressive_strategy = aggressive_payload["strategy"]
        assert aggressive_strategy["strategy"] == "ds_aggressive"
        assert aggressive_strategy["latest_ds_rejection"]["rejection_id"] == "DSX-DS_AGGRESSIVE-VERIFY"
        assert "risk gate required smaller target weight" in aggressive_strategy["latest_ds_rejection"]["reason"]
        assert "recent_events" in aggressive_strategy

        head, body = roundtrip(handler, http_request("GET", "/", headers=bearer("dash-token")))
        assert b"200" in head.split(b"\r\n", 1)[0]
        html = body.decode("utf-8")
        assert "模拟交易监控台" in html
        assert "const I18N =" in html
        assert 'id="lang-select"' in html
        assert 'id="mode-badge"' in html
        assert 'id="strategy-tabs"' in html
        assert 'id="overview-view"' in html
        assert 'id="strategy-view"' in html
        assert 'id="strategy-kpis"' in html
        assert 'id="nav-chart"' in html
        assert 'id="strategy-nav-chart"' in html
        assert 'id="price-trends-grid"' in html
        assert 'id="execution-status"' in html
        assert 'id="risk-gate-status"' in html
        assert 'id="validation-status"' in html
        assert 'id="ds-status"' in html
        assert 'id="execution-list"' in html
        assert 'id="risk-list"' in html
        assert 'id="validation-list"' in html
        assert 'id="ds-list"' in html
        assert 'id="ds-rejection-list"' in html
        assert 'id="strategy-trades-body"' in html
        assert 'id="strategy-events-list"' in html

    print("normalization-audit: ok")
    print("dashboard-payload-structure: ok")
    print("phase2-api-fields: ok")
    print("ds-status-fields: ok")
    print("strategy-tabs-data: ok")
    print("strategy-detail-endpoint: ok")
    print("dashboard-html-critical-fields: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
