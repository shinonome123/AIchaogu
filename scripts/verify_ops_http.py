from __future__ import annotations

import base64
import json
import os
import socket
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim_trading.ledger import LedgerService
from sim_trading.notifier import notify_task
from sim_trading.security import DashboardAuthConfig
from sim_trading.servers import DashboardServerConfig, WebhookServerConfig, make_dashboard_handler, make_webhook_handler
from sim_trading.storage import append_jsonl


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


def http_request(method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None) -> bytes:
    lines = [f"{method} {path} HTTP/1.0", "Host: localhost", "Connection: close"]
    for key, value in (headers or {}).items():
        lines.append(f"{key}: {value}")
    if body:
        lines.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body


def _basic_auth(username: str, password: str) -> str:
    payload = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {payload}"


def _prepare_demo_state(state_dir: Path, report_log: Path) -> None:
    service = LedgerService(state_dir)
    service.initialize_from_seed(ROOT / "seeds/initial_state.json")
    service.save_market_prices(
        {
            "BTC/USDT": {"price": "41", "timestamp": "2026-03-11T09:00:00+08:00"},
            "DOT/USDT": {"price": "8", "timestamp": "2026-03-11T09:00:00+08:00"},
            "LINK/USDT": {"price": "19", "timestamp": "2026-03-11T09:00:00+08:00"},
        }
    )
    append_jsonl(
        service.paths.market_feed,
        {
            "timestamp": "2026-03-11T09:00:00+08:00",
            "source": "verification",
            "symbols": ["BTC/USDT", "DOT/USDT", "LINK/USDT"],
            "prices": {
                "BTC/USDT": {"price": "41", "timestamp": "2026-03-11T09:00:00+08:00", "source": "verification"},
                "DOT/USDT": {"price": "8", "timestamp": "2026-03-11T09:00:00+08:00", "source": "verification"},
                "LINK/USDT": {"price": "19", "timestamp": "2026-03-11T09:00:00+08:00", "source": "verification"},
            },
        },
    )
    append_jsonl(
        service.paths.signal_runs,
        {
            "timestamp": "2026-03-11T09:05:00+08:00",
            "source": "verification",
            "market_timestamp": "2026-03-11T09:00:00+08:00",
            "lookback_points": 3,
            "signal_count": 3,
            "bullish_count": 2,
            "bearish_count": 0,
            "status": "ok",
            "summary": "2 bullish / 0 bearish / 3 total",
            "signals": [
                {"symbol": "BTC/USDT", "signal": "bullish", "observations": 3, "momentum": "0.03", "ema_slope": "0.2", "latest_price": "41"},
                {"symbol": "DOT/USDT", "signal": "flat", "observations": 3, "momentum": "0.01", "ema_slope": "0", "latest_price": "8"},
                {"symbol": "LINK/USDT", "signal": "bullish", "observations": 3, "momentum": "0.02", "ema_slope": "0.1", "latest_price": "19"},
            ],
            "targets": [{"symbol": "BTC/USDT", "target_weight": "0.4", "rationale": "verification"}],
        },
    )
    notify_task(
        report_log=report_log,
        task="verification",
        status="ok",
        did_what="Prepared dashboard verification payload.",
        risk_impact="No portfolio change.",
        next_step="Exercise the HTTP handlers.",
        source="verification.setup",
        timestamp="2026-03-11T09:06:00+08:00",
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        state_dir = tmp / "state"
        report_log = tmp / "reports-log.jsonl"
        _prepare_demo_state(state_dir, report_log)
        now_iso = datetime.now().astimezone().isoformat(timespec="seconds")

        os.environ["SIM_TRADING_WEBHOOK_TOKEN"] = "test-token"
        webhook_handler = make_webhook_handler(
            WebhookServerConfig(
                state_dir=state_dir,
                report_log=report_log,
                token_env="SIM_TRADING_WEBHOOK_TOKEN",
                replay_ttl_seconds=300,
            )
        )

        valid_body = json.dumps(
            {
                "task": "webhook-test",
                "status": "ok",
                "did_what": "Verified webhook handler via socketpair.",
                "risk_impact": "No portfolio change.",
                "next_step": "Inspect dashboard payload.",
                "source": "verification.webhook",
                "token": "test-token",
                "nonce": "nonce-1",
                "timestamp": now_iso,
            }
        ).encode("utf-8")
        head, body = roundtrip(
            webhook_handler,
            http_request("POST", "/task-done", valid_body, {"Content-Type": "application/json"}),
        )
        payload = json.loads(body.decode("utf-8"))
        assert b"200" in head.split(b"\r\n", 1)[0]
        assert payload["ok"] is True

        head, body = roundtrip(
            webhook_handler,
            http_request("POST", "/task-done", valid_body, {"Content-Type": "application/json"}),
        )
        duplicate_payload = json.loads(body.decode("utf-8"))
        assert b"409" in head.split(b"\r\n", 1)[0]
        assert duplicate_payload["error"] == "nonce already used"

        missing_token_body = json.dumps(
            {
                "task": "webhook-test",
                "status": "ok",
                "did_what": "missing token",
                "risk_impact": "n/a",
                "next_step": "n/a",
                "nonce": "nonce-2",
                "timestamp": now_iso,
            }
        ).encode("utf-8")
        head, body = roundtrip(
            webhook_handler,
            http_request("POST", "/task-done", missing_token_body, {"Content-Type": "application/json"}),
        )
        missing_payload = json.loads(body.decode("utf-8"))
        assert b"401" in head.split(b"\r\n", 1)[0]
        assert missing_payload["error"] == "missing token"

        stale_body = json.dumps(
            {
                "task": "webhook-test",
                "status": "ok",
                "did_what": "stale timestamp",
                "risk_impact": "n/a",
                "next_step": "n/a",
                "source": "verification.webhook",
                "token": "test-token",
                "nonce": "nonce-3",
                "timestamp": "2020-03-11T09:10:00+08:00",
            }
        ).encode("utf-8")
        head, body = roundtrip(
            webhook_handler,
            http_request("POST", "/task-done", stale_body, {"Content-Type": "application/json"}),
        )
        stale_payload = json.loads(body.decode("utf-8"))
        assert b"403" in head.split(b"\r\n", 1)[0]
        assert "replay TTL" in stale_payload["error"]

        dashboard_handler = make_dashboard_handler(
            DashboardServerConfig(
                state_dir=state_dir.resolve(),
                report_log=report_log.resolve(),
                notification_limit=3,
                auth=DashboardAuthConfig(
                    bearer_token="dash-token",
                    basic_username="ops",
                    basic_password="dash-pass",
                ),
            )
        )

        head, body = roundtrip(dashboard_handler, http_request("GET", "/"))
        assert b"401" in head.split(b"\r\n", 1)[0]
        assert b"WWW-Authenticate" in head

        head, body = roundtrip(dashboard_handler, http_request("GET", "/api/health"))
        health_payload = json.loads(body.decode("utf-8"))
        assert b"200" in head.split(b"\r\n", 1)[0]
        assert "checks" in health_payload

        head, body = roundtrip(
            dashboard_handler,
            http_request("GET", "/api/status?n=2", headers={"Authorization": "Bearer dash-token"}),
        )
        api_payload = json.loads(body.decode("utf-8"))
        assert b"200" in head.split(b"\r\n", 1)[0]
        assert b"Set-Cookie" in head
        assert api_payload["ok"] is True
        assert api_payload["latest_market_fetch"]["timestamp"] == "2026-03-11T09:00:00+08:00"
        assert api_payload["latest_signal_run"]["summary"] == "2 bullish / 0 bearish / 3 total"
        assert "timeseries" in api_payload["snapshot"]
        assert len(api_payload["snapshot"]["timeseries"]["equity_curve"]) >= 1
        assert "BTC/USDT" in api_payload["snapshot"]["timeseries"]["market_prices"]
        assert len(api_payload["latest_notifications"]) <= 2

        head, body = roundtrip(
            dashboard_handler,
            http_request(
                "GET",
                "/api/status?n=1",
                headers={"Authorization": _basic_auth("ops", "dash-pass")},
            ),
        )
        basic_payload = json.loads(body.decode("utf-8"))
        assert b"200" in head.split(b"\r\n", 1)[0]
        assert basic_payload["ok"] is True

        head, body = roundtrip(
            dashboard_handler,
            http_request("GET", "/", headers={"Authorization": "Bearer dash-token"}),
        )
        assert b"200" in head.split(b"\r\n", 1)[0]
        assert "模拟交易监控台".encode("utf-8") in body
        assert b'id="lang-select"' in body
        assert b'id="nav-chart"' in body
        assert b'id="price-trends-grid"' in body

    print("webhook-security: ok")
    print("dashboard-auth: ok")
    print("dashboard-health: ok")
    print("dashboard-timeseries: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
