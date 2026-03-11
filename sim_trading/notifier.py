from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sim_trading.models import now_iso
from sim_trading.storage import append_jsonl, read_jsonl

AUTO_REPORT_ENV = "SIM_TRADING_AUTO_REPORT"
DEFAULT_HOOK_ENV = "SIM_TRADING_NOTIFY_HOOK"
DEFAULT_WEBHOOK_TOKEN_ENV = "SIM_TRADING_WEBHOOK_TOKEN"


@dataclass(frozen=True)
class NotifyResult:
    entry: dict[str, Any]
    report_log: Path
    hook_command: str | None
    hook_returncode: int | None
    hook_stdout: str
    hook_stderr: str


def default_report_log_path(state_dir: Path | str) -> Path:
    return Path(state_dir).resolve().parent / "reports-log.jsonl"


def build_report_payload(
    *,
    task: str,
    status: str,
    did_what: str,
    risk_impact: str,
    next_step: str,
    source: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    task_name = task.strip()
    current_status = status.strip()
    source_name = source.strip()
    if not task_name:
        raise ValueError("task is required")
    if not current_status:
        raise ValueError("status is required")
    if not source_name:
        raise ValueError("source is required")

    return {
        "timestamp": timestamp or now_iso(),
        "task": task_name,
        "status": current_status,
        "current_status": current_status,
        "did_what": did_what.strip(),
        "risk_impact": risk_impact.strip(),
        "next_step": next_step.strip(),
        "source": source_name,
    }


def append_report_entry(report_log: Path | str, payload: dict[str, Any]) -> Path:
    path = Path(report_log)
    append_jsonl(path, payload)
    return path


def resolve_hook_command(override: str | None = None) -> str | None:
    hook_command = override if override is not None else os.getenv(DEFAULT_HOOK_ENV)
    return hook_command.strip() if hook_command else None


def run_shell_hook(hook_command: str | None, *, payload: dict[str, Any], report_log: Path) -> tuple[int | None, str, str]:
    if not hook_command:
        return None, "", ""

    env = os.environ.copy()
    env["SIM_TRADING_REPORT_PAYLOAD"] = json.dumps(payload, sort_keys=True)
    env["SIM_TRADING_REPORT_LOG"] = str(report_log)
    completed = subprocess.run(
        hook_command,
        shell=True,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def notify_task(
    *,
    report_log: Path | str,
    task: str,
    status: str,
    did_what: str,
    risk_impact: str,
    next_step: str,
    source: str,
    hook_command: str | None = None,
    timestamp: str | None = None,
) -> NotifyResult:
    entry = build_report_payload(
        task=task,
        status=status,
        did_what=did_what,
        risk_impact=risk_impact,
        next_step=next_step,
        source=source,
        timestamp=timestamp,
    )
    path = append_report_entry(report_log, entry)
    command = resolve_hook_command(hook_command)
    hook_returncode, hook_stdout, hook_stderr = run_shell_hook(command, payload=entry, report_log=path)
    return NotifyResult(
        entry=entry,
        report_log=path,
        hook_command=command,
        hook_returncode=hook_returncode,
        hook_stdout=hook_stdout,
        hook_stderr=hook_stderr,
    )


def load_report_entries(report_log: Path | str, limit: int = 20) -> list[dict[str, Any]]:
    entries = [item for item in read_jsonl(Path(report_log)) if isinstance(item, dict)]
    if limit >= 0:
        entries = entries[-limit:] if limit else []
    entries.reverse()
    return entries


def human_summary(result: NotifyResult) -> str:
    lines = [
        f"Task: {result.entry['task']}",
        f"Status: {result.entry['current_status']}",
        f"Did what: {result.entry['did_what']}",
        f"Risk impact: {result.entry['risk_impact']}",
        f"Next step: {result.entry['next_step']}",
        f"Source: {result.entry['source']}",
        f"Timestamp: {result.entry['timestamp']}",
        f"Report log: {result.report_log}",
    ]
    if result.hook_command:
        lines.append(f"Hook: {result.hook_command} (exit={result.hook_returncode})")
    else:
        lines.append("Hook: not configured")
    return "\n".join(lines)


def auto_reporting_enabled() -> bool:
    return os.getenv(AUTO_REPORT_ENV, "1").strip().lower() not in {"0", "false", "no", "off"}
