from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sim_trading.dashboard_data import build_status_snapshot
from sim_trading.models import decimal_to_money, now_iso
from sim_trading.notifier import NotifyResult, notify_task
from sim_trading.storage import StoragePaths, read_last_jsonl


def _status_level(snapshot: dict[str, Any]) -> str:
    drawdown = Decimal(snapshot["drawdown_pct"])
    risk_status = snapshot.get("risk_status", {}) if isinstance(snapshot.get("risk_status"), dict) else {}
    if snapshot["breached_stop_losses"]:
        return "alert"
    if bool(risk_status.get("blocked_new_orders")):
        return "watch"
    if drawdown <= Decimal("-0.05"):
        return "watch"
    return "ok"


def _risk_impact(snapshot: dict[str, Any]) -> str:
    drawdown = Decimal(snapshot["drawdown_pct"])
    parts: list[str] = []
    risk_status = snapshot.get("risk_status", {}) if isinstance(snapshot.get("risk_status"), dict) else {}
    if snapshot.get("position_mode_is_normalized"):
        parts.append("Position seed holdings are already in normalized notional mode.")
    elif snapshot.get("position_requires_normalization"):
        parts.append("Legacy synthetic seed-unit positions still need normalization before NAV is comparable to market marks.")
    if bool(risk_status.get("blocked_new_orders")):
        parts.append("Execution risk gates are blocking new buy orders: " + "; ".join(risk_status.get("blocked_reasons", [])))
    if snapshot.get("ds_mode") == "approval":
        parts.append("A DS-approved simulation plan is waiting for one execution cycle.")
    if snapshot["breached_stop_losses"]:
        parts.append(f"Stop-loss breached for {', '.join(snapshot['breached_stop_losses'])}.")
    if drawdown < 0:
        parts.append(f"Portfolio drawdown is {drawdown:.2%} from peak.")
    unrealized = Decimal(snapshot["unrealized_pnl_total"])
    if unrealized < 0:
        parts.append(f"Open positions carry {decimal_to_money(unrealized)} unrealized PnL.")
    if not parts:
        return "Normal operating range. No stop-loss breaches and drawdown is flat."
    return " ".join(parts)


def _next_step(snapshot: dict[str, Any]) -> str:
    risk_status = snapshot.get("risk_status", {}) if isinstance(snapshot.get("risk_status"), dict) else {}
    if snapshot.get("position_requires_normalization"):
        return "Run normalize-positions after refreshing market prices so NAV reflects carrying notionals instead of synthetic seed units."
    if snapshot.get("ds_mode") == "approval":
        return "Run execute-sim --decision-source ds-approved when you want to consume the latest approved DS plan."
    if bool(risk_status.get("blocked_new_orders")):
        return "Inspect risk-status, clear the kill switch or cooldown if appropriate, and review the last circuit-breaker event before the next execution cycle."
    if snapshot["breached_stop_losses"]:
        return "Review breached stops and decide whether to reduce or close exposure."
    if Decimal(snapshot["drawdown_pct"]) <= Decimal("-0.05"):
        return "Refresh marks, review position sizing, and continue tighter monitoring."
    return "Continue scheduled monitoring and emit the next status report."


def emit_status_report(
    *,
    state_dir: Path | str,
    report_log: Path | str,
    source: str = "cli.emit-status-report",
    task: str = "ledger-status",
    hook_command: str | None = None,
    timestamp: str | None = None,
) -> NotifyResult:
    snapshot = build_status_snapshot(state_dir=state_dir, timestamp=timestamp)
    position_mode = snapshot["position_mode_summary"]
    did_what = (
        "Generated live status snapshot "
        + f"({position_mode}; NAV {decimal_to_money(snapshot['nav'])}, realized {decimal_to_money(snapshot['realized_pnl_total'])}, "
        + f"unrealized {decimal_to_money(snapshot['unrealized_pnl_total'])}, positions {snapshot['position_count']})."
    )
    return notify_task(
        report_log=report_log,
        task=task,
        status=_status_level(snapshot),
        did_what=did_what,
        risk_impact=_risk_impact(snapshot),
        next_step=_next_step(snapshot),
        source=source,
        hook_command=hook_command,
        timestamp=timestamp,
    )


def _parse_timestamp(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _status_for_checks(checks: list[dict[str, Any]]) -> str:
    if any(not item["ok"] for item in checks):
        return "alert"
    return "ok"


def _pid_from_file(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _probe_dashboard_health(url: str, *, timeout_seconds: int) -> tuple[bool, str]:
    request = Request(url, headers={"User-Agent": "sim-trading/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                return False, f"dashboard health returned HTTP {response.status}"
            return True, "dashboard health endpoint responded"
    except HTTPError as exc:
        return False, f"dashboard health returned HTTP {exc.code}"
    except URLError as exc:
        return False, f"dashboard health probe failed: {exc.reason}"


def _probe_tcp(host: str, port: int, *, timeout_seconds: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True, f"tcp connect ok to {host}:{port}"
    except OSError as exc:
        return False, f"tcp connect failed to {host}:{port}: {exc}"


def build_health_snapshot(
    *,
    state_dir: Path | str,
    report_log: Path | str,
    max_report_age_seconds: int = 7200,
    dashboard_pid_file: Path | str | None = None,
    webhook_pid_file: Path | str | None = None,
    dashboard_health_url: str | None = None,
    webhook_host: str | None = None,
    webhook_port: int | None = None,
    timeout_seconds: int = 3,
) -> dict[str, Any]:
    paths = StoragePaths(Path(state_dir))
    required_files = [
        ("account", paths.account),
        ("config", paths.config),
        ("positions", paths.positions),
        ("market_prices", paths.market_prices),
        ("risk_state", paths.risk_state),
        ("trades", paths.trades),
        ("equity_curve", paths.equity_curve),
    ]
    state_checks = [
        {
            "name": name,
            "path": str(path),
            "ok": path.exists(),
            "detail": "present" if path.exists() else "missing",
        }
        for name, path in required_files
    ]

    report_log_path = Path(report_log)
    last_report = read_last_jsonl(report_log_path)
    report_timestamp = (
        _parse_timestamp(str(last_report.get("timestamp"))) if isinstance(last_report, dict) else None
    )
    now = datetime.now(timezone.utc)
    report_age_seconds = int((now - report_timestamp).total_seconds()) if report_timestamp else None
    report_ok = report_log_path.exists() and report_timestamp is not None and report_age_seconds is not None
    if report_ok and report_age_seconds is not None:
        report_ok = report_age_seconds <= max_report_age_seconds
    report_check = {
        "name": "report_log_freshness",
        "path": str(report_log_path),
        "ok": report_ok,
        "detail": (
            f"latest entry age {report_age_seconds}s"
            if report_age_seconds is not None
            else "missing or unreadable latest report entry"
        ),
    }

    service_checks: list[dict[str, Any]] = []
    if dashboard_pid_file is not None:
        dashboard_pid_path = Path(dashboard_pid_file)
        dashboard_pid = _pid_from_file(dashboard_pid_path)
        service_checks.append(
            {
                "name": "dashboard_pid",
                "path": str(dashboard_pid_path),
                "ok": _pid_alive(dashboard_pid),
                "detail": f"pid {dashboard_pid}" if dashboard_pid is not None else "missing or invalid pid file",
            }
        )
    if webhook_pid_file is not None:
        webhook_pid_path = Path(webhook_pid_file)
        webhook_pid = _pid_from_file(webhook_pid_path)
        service_checks.append(
            {
                "name": "webhook_pid",
                "path": str(webhook_pid_path),
                "ok": _pid_alive(webhook_pid),
                "detail": f"pid {webhook_pid}" if webhook_pid is not None else "missing or invalid pid file",
            }
        )
    if dashboard_health_url:
        ok, detail = _probe_dashboard_health(dashboard_health_url, timeout_seconds=timeout_seconds)
        service_checks.append(
            {
                "name": "dashboard_http",
                "path": dashboard_health_url,
                "ok": ok,
                "detail": detail,
            }
        )
    if webhook_host and webhook_port:
        ok, detail = _probe_tcp(webhook_host, webhook_port, timeout_seconds=timeout_seconds)
        service_checks.append(
            {
                "name": "webhook_tcp",
                "path": f"{webhook_host}:{webhook_port}",
                "ok": ok,
                "detail": detail,
            }
        )

    all_checks = state_checks + [report_check] + service_checks
    return {
        "ok": all(item["ok"] for item in all_checks),
        "status": _status_for_checks(all_checks),
        "timestamp": now_iso(),
        "state_dir": str(Path(state_dir).resolve()),
        "report_log": str(report_log_path.resolve()),
        "max_report_age_seconds": max_report_age_seconds,
        "checks": all_checks,
    }


def format_health_lines(snapshot: dict[str, Any]) -> list[str]:
    lines = [
        f"Health: {snapshot['status']}",
        f"Checked at: {snapshot['timestamp']}",
        f"State dir: {snapshot['state_dir']}",
        f"Report log: {snapshot['report_log']}",
    ]
    for check in snapshot["checks"]:
        marker = "ok" if check["ok"] else "fail"
        lines.append(f"[{marker}] {check['name']} {check['detail']} ({check['path']})")
    return lines
