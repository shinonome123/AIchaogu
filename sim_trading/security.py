from __future__ import annotations

import base64
import hmac
import secrets
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from sim_trading.storage import read_json, write_json

DEFAULT_WEBHOOK_TOKEN_ENV = "SIM_TRADING_WEBHOOK_TOKEN"
DEFAULT_DASHBOARD_BEARER_ENV = "SIM_TRADING_DASHBOARD_BEARER_TOKEN"
DEFAULT_DASHBOARD_BASIC_USER_ENV = "SIM_TRADING_DASHBOARD_BASIC_USER"
DEFAULT_DASHBOARD_BASIC_PASS_ENV = "SIM_TRADING_DASHBOARD_BASIC_PASS"
DEFAULT_WEBHOOK_REPLAY_TTL_ENV = "SIM_TRADING_WEBHOOK_REPLAY_TTL_SECONDS"

OPS_ENV_TEMPLATE = """# sim-trading ops environment
# Source this file before using the guarded ops scripts:
#   set -a && . ./.ops.env && set +a
SIM_TRADING_STATE_DIR=demo/state
SIM_TRADING_REPORT_LOG=demo/reports-log.jsonl
SIM_TRADING_DASHBOARD_HOST=127.0.0.1
SIM_TRADING_DASHBOARD_PORT=8780
SIM_TRADING_WEBHOOK_HOST=127.0.0.1
SIM_TRADING_WEBHOOK_PORT=8765
SIM_TRADING_WEBHOOK_REPLAY_TTL_SECONDS=300
SIM_TRADING_DASHBOARD_BASIC_USER=ops
SIM_TRADING_NOTIFY_HOOK=
"""


def generate_secret() -> str:
    return secrets.token_urlsafe(32)


def redact_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


@dataclass(frozen=True)
class DashboardAuthConfig:
    bearer_token: str | None = None
    basic_username: str | None = None
    basic_password: str | None = None
    bearer_env: str = DEFAULT_DASHBOARD_BEARER_ENV
    basic_user_env: str = DEFAULT_DASHBOARD_BASIC_USER_ENV
    basic_pass_env: str = DEFAULT_DASHBOARD_BASIC_PASS_ENV

    def is_configured(self) -> bool:
        return bool(self.bearer_token or (self.basic_username and self.basic_password))

    def enabled_methods(self) -> list[str]:
        methods: list[str] = []
        if self.bearer_token:
            methods.append(f"bearer:{self.bearer_env}")
        if self.basic_username and self.basic_password:
            methods.append(f"basic:{self.basic_user_env}/{self.basic_pass_env}")
        return methods

    def authenticate(self, authorization_header: str | None, *, cookie_token: str | None = None) -> tuple[bool, int, str | None]:
        if not self.is_configured():
            return True, 200, None
        if self.bearer_token and cookie_token and hmac.compare_digest(cookie_token, self.bearer_token):
            return True, 200, None
        if not authorization_header:
            return False, 401, "missing Authorization header"

        scheme, _, value = authorization_header.partition(" ")
        normalized_scheme = scheme.strip().lower()
        token = value.strip()
        if not normalized_scheme or not token:
            return False, 401, "malformed Authorization header"

        if normalized_scheme == "bearer":
            if not self.bearer_token:
                return False, 403, "bearer auth is not enabled"
            if hmac.compare_digest(token, self.bearer_token):
                return True, 200, None
            return False, 403, "invalid bearer token"

        if normalized_scheme == "basic":
            if not (self.basic_username and self.basic_password):
                return False, 403, "basic auth is not enabled"
            try:
                raw_bytes = base64.b64decode(token.encode("ascii"), validate=True)
                username, password = raw_bytes.decode("utf-8").split(":", 1)
            except Exception:
                return False, 401, "invalid basic auth encoding"
            if hmac.compare_digest(username, self.basic_username) and hmac.compare_digest(
                password, self.basic_password
            ):
                return True, 200, None
            return False, 403, "invalid basic credentials"

        return False, 401, "unsupported authorization scheme"

    def challenge_value(self) -> str:
        if self.basic_username and self.basic_password:
            return 'Basic realm="Sim Trading Dashboard", charset="UTF-8"'
        return 'Bearer realm="Sim Trading Dashboard"'


@dataclass(frozen=True)
class ReplayValidationResult:
    ok: bool
    status_code: int
    error: str | None = None


class ReplayNonceStore:
    def __init__(self, path: Path, ttl_seconds: int) -> None:
        self.path = path
        self.ttl_seconds = max(0, int(ttl_seconds))
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    def validate(self, *, nonce: str, timestamp: str) -> ReplayValidationResult:
        if not self.enabled:
            return ReplayValidationResult(ok=True, status_code=200)

        if not timestamp.strip():
            return ReplayValidationResult(
                ok=False,
                status_code=401,
                error="timestamp is required when replay protection is enabled",
            )
        if not nonce.strip():
            return ReplayValidationResult(
                ok=False,
                status_code=401,
                error="nonce is required when replay protection is enabled",
            )

        try:
            request_time = datetime.fromisoformat(timestamp)
        except ValueError:
            return ReplayValidationResult(ok=False, status_code=400, error="timestamp must be ISO-8601")
        if request_time.tzinfo is None:
            return ReplayValidationResult(ok=False, status_code=400, error="timestamp must include timezone offset")

        now = datetime.now(timezone.utc)
        request_time_utc = request_time.astimezone(timezone.utc)
        age_seconds = abs((now - request_time_utc).total_seconds())
        if age_seconds > self.ttl_seconds:
            return ReplayValidationResult(
                ok=False,
                status_code=403,
                error=f"timestamp outside replay TTL ({self.ttl_seconds}s)",
            )

        with self._lock:
            payload = read_json(self.path, default={})
            entries = payload if isinstance(payload, dict) else {}
            pruned = self._prune_entries(entries, now)
            if nonce in pruned:
                return ReplayValidationResult(ok=False, status_code=409, error="nonce already used")
            pruned[nonce] = request_time_utc.isoformat()
            write_json(self.path, pruned)

        return ReplayValidationResult(ok=True, status_code=200)

    def _prune_entries(self, entries: Mapping[str, str], now: datetime) -> dict[str, str]:
        cutoff = now.timestamp() - self.ttl_seconds
        pruned: dict[str, str] = {}
        for nonce, raw_timestamp in entries.items():
            try:
                seen_at = datetime.fromisoformat(str(raw_timestamp)).astimezone(timezone.utc)
            except ValueError:
                continue
            if seen_at.timestamp() >= cutoff:
                pruned[nonce] = seen_at.isoformat()
        return pruned


def upsert_env_file(path: Path, updates: Mapping[str, str], *, create_template: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = existing_lines[:] if existing_lines else (OPS_ENV_TEMPLATE.strip().splitlines() if create_template else [])
    seen: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _, _ = line.partition("=")
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")

    rendered = "\n".join(new_lines).rstrip() + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(rendered)
        temp_path = Path(handle.name)
    temp_path.replace(path)
    path.chmod(0o600)
