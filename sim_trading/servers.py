from __future__ import annotations

import json
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from sim_trading.dashboard_data import build_dashboard_status_payload, build_strategy_detail
from sim_trading.experiments import load_experiment_runs, load_latest_experiment_run
from sim_trading.dashboard_ui import render_dashboard_page
from sim_trading.notifier import notify_task
from sim_trading.ops import build_health_snapshot
from sim_trading.security import DashboardAuthConfig, ReplayNonceStore
from sim_trading.storage import StoragePaths
from sim_trading.strategy_tracks import resolve_strategy_profile


@dataclass(frozen=True)
class WebhookServerConfig:
    state_dir: Path
    report_log: Path
    token_env: str
    hook_command: str | None = None
    replay_ttl_seconds: int = 0


@dataclass(frozen=True)
class DashboardServerConfig:
    state_dir: Path
    report_log: Path
    notification_limit: int = 20
    auth: DashboardAuthConfig = DashboardAuthConfig()
    health_max_report_age_seconds: int = 7200


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_length = handler.headers.get("Content-Length")
    if not raw_length:
        raise ValueError("missing Content-Length")
    length = int(raw_length)
    if length <= 0:
        raise ValueError("request body is empty")
    raw_body = handler.rfile.read(length)
    payload = json.loads(raw_body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _send_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
    *,
    extra_headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    for key, value in (extra_headers or {}).items():
        handler.send_header(key, value)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_html(handler: BaseHTTPRequestHandler, html: str, *, extra_headers: dict[str, str] | None = None) -> None:
    body = html.encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    for key, value in (extra_headers or {}).items():
        handler.send_header(key, value)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _cookie_value(handler: BaseHTTPRequestHandler, key: str) -> str | None:
    cookie_header = handler.headers.get("Cookie", "")
    for chunk in cookie_header.split(";"):
        name, separator, value = chunk.strip().partition("=")
        if separator and name == key:
            return value
    return None


def _bearer_value(handler: BaseHTTPRequestHandler) -> str | None:
    authorization = handler.headers.get("Authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.strip().lower() != "bearer":
        return None
    return value.strip() or None


def _dashboard_auth_headers(config: DashboardServerConfig) -> dict[str, str]:
    return {"WWW-Authenticate": config.auth.challenge_value()}


def _check_dashboard_auth(
    handler: BaseHTTPRequestHandler,
    config: DashboardServerConfig,
) -> tuple[bool, dict[str, str]]:
    cookie_token = _cookie_value(handler, "sim_trading_dashboard_token")
    ok, status, error = config.auth.authenticate(
        handler.headers.get("Authorization"),
        cookie_token=cookie_token,
    )
    if ok:
        headers: dict[str, str] = {}
        bearer_value = _bearer_value(handler)
        if bearer_value and config.auth.bearer_token and bearer_value == config.auth.bearer_token:
            headers["Set-Cookie"] = (
                f"sim_trading_dashboard_token={config.auth.bearer_token}; Path=/; HttpOnly; SameSite=Strict"
            )
        return True, headers

    _send_json(
        handler,
        status,
        {"ok": False, "error": error},
        extra_headers=_dashboard_auth_headers(config) if status == HTTPStatus.UNAUTHORIZED else None,
    )
    return False, {}


def make_webhook_handler(config: WebhookServerConfig) -> type[BaseHTTPRequestHandler]:
    replay_store = ReplayNonceStore(StoragePaths(config.state_dir).webhook_nonces, config.replay_ttl_seconds)

    class WebhookHandler(BaseHTTPRequestHandler):
        server_version = "SimTradingWebhook/0.3"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            if urlsplit(self.path).path != "/task-done":
                _send_json(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "unknown endpoint"})
                return

            expected_token = os.getenv(config.token_env)
            if not expected_token:
                _send_json(
                    self,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"ok": False, "error": f"webhook token env '{config.token_env}' is not configured"},
                )
                return

            try:
                payload = _read_json_body(self)
                token = str(payload.get("token", ""))
                if not token:
                    _send_json(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "missing token"})
                    return
                if token != expected_token:
                    _send_json(self, HTTPStatus.FORBIDDEN, {"ok": False, "error": "invalid token"})
                    return
                replay_result = replay_store.validate(
                    nonce=str(payload.get("nonce", "")),
                    timestamp=str(payload.get("timestamp", "")),
                )
                if not replay_result.ok:
                    _send_json(
                        self,
                        replay_result.status_code,
                        {"ok": False, "error": replay_result.error},
                    )
                    return

                result = notify_task(
                    report_log=config.report_log,
                    task=str(payload.get("task", "")),
                    status=str(payload.get("status", "")),
                    did_what=str(payload.get("did_what", "")),
                    risk_impact=str(payload.get("risk_impact", "")),
                    next_step=str(payload.get("next_step", "")),
                    source=str(payload.get("source", "webhook.task-done")),
                    hook_command=config.hook_command,
                    timestamp=str(payload.get("timestamp", "")).strip() or None,
                )
            except ValueError as exc:
                _send_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            except json.JSONDecodeError as exc:
                _send_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"invalid JSON: {exc.msg}"})
                return
            except Exception as exc:  # pragma: no cover - server boundary
                _send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
                return

            _send_json(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "entry": result.entry,
                    "report_log": str(result.report_log),
                    "hook": {
                        "command": result.hook_command,
                        "returncode": result.hook_returncode,
                        "stdout": result.hook_stdout,
                        "stderr": result.hook_stderr,
                    },
                },
            )

    return WebhookHandler


def _strategy_name_from_query(handler: BaseHTTPRequestHandler) -> str:
    query = parse_qs(urlsplit(handler.path).query)
    raw_name = str(query.get("name", [""])[0]).strip().lower()
    if not raw_name:
        raise ValueError("missing strategy name")
    resolve_strategy_profile(raw_name)
    return raw_name


def make_dashboard_handler(config: DashboardServerConfig) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "SimTradingDashboard/0.4"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            if parsed.path == "/api/health":
                try:
                    payload = build_health_snapshot(
                        state_dir=config.state_dir,
                        report_log=config.report_log,
                        max_report_age_seconds=config.health_max_report_age_seconds,
                    )
                except Exception as exc:  # pragma: no cover - server boundary
                    _send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
                    return
                _send_json(self, HTTPStatus.OK, payload)
                return

            if parsed.path in {"/", "/api/status", "/api/strategy", "/api/experiments/latest", "/api/experiments/history"} and config.auth.is_configured():
                authorized, auth_headers = _check_dashboard_auth(self, config)
                if not authorized:
                    return
            else:
                auth_headers = {}

            if parsed.path == "/":
                _send_html(self, render_dashboard_page(config.notification_limit), extra_headers=auth_headers)
                return

            if parsed.path == "/api/status":
                query = parse_qs(parsed.query)
                limit = config.notification_limit
                if "n" in query:
                    try:
                        limit = max(0, int(query["n"][0]))
                    except ValueError:
                        _send_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid n query parameter"})
                        return

                try:
                    payload = build_dashboard_status_payload(
                        state_dir=config.state_dir,
                        report_log=config.report_log,
                        notification_limit=limit,
                    )
                except Exception as exc:  # pragma: no cover - server boundary
                    _send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
                    return
                _send_json(self, HTTPStatus.OK, payload, extra_headers=auth_headers)
                return

            if parsed.path == "/api/strategy":
                try:
                    strategy_name = _strategy_name_from_query(self)
                except ValueError as exc:
                    _send_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return

                try:
                    payload = {
                        "ok": True,
                        "strategy": build_strategy_detail(
                            config.state_dir,
                            strategy=strategy_name,
                        ),
                    }
                except Exception as exc:  # pragma: no cover - server boundary
                    _send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
                    return
                _send_json(self, HTTPStatus.OK, payload, extra_headers=auth_headers)
                return

            if parsed.path == "/api/experiments/latest":
                _send_json(
                    self,
                    HTTPStatus.OK,
                    {"ok": True, "latest_experiment_run": load_latest_experiment_run(config.state_dir)},
                    extra_headers=auth_headers,
                )
                return

            if parsed.path == "/api/experiments/history":
                query = parse_qs(parsed.query)
                limit = 20
                if "n" in query:
                    try:
                        limit = max(1, min(200, int(query["n"][0])))
                    except ValueError:
                        _send_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid n query parameter"})
                        return
                _send_json(
                    self,
                    HTTPStatus.OK,
                    {"ok": True, "items": load_experiment_runs(config.state_dir, limit=limit)},
                    extra_headers=auth_headers,
                )
                return

            _send_json(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "unknown endpoint"})

    return DashboardHandler


def create_webhook_server(*, host: str, port: int, config: WebhookServerConfig) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_webhook_handler(config))


def create_dashboard_server(*, host: str, port: int, config: DashboardServerConfig) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_dashboard_handler(config))


def serve_webhook(*, host: str, port: int, config: WebhookServerConfig) -> None:
    with create_webhook_server(host=host, port=port, config=config) as httpd:
        httpd.serve_forever()


def serve_dashboard(*, host: str, port: int, config: DashboardServerConfig) -> None:
    with create_dashboard_server(host=host, port=port, config=config) as httpd:
        httpd.serve_forever()
