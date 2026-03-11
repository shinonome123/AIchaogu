from __future__ import annotations

from functools import lru_cache
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().with_name("dashboard_assets")


@lru_cache(maxsize=None)
def _asset_text(name: str) -> str:
    return (ASSET_ROOT / name).read_text(encoding="utf-8")


def render_dashboard_page(notification_limit: int) -> str:
    template = _asset_text("dashboard.html")
    return (
        template.replace("__DASHBOARD_CSS__", _asset_text("dashboard.css"))
        .replace("__DASHBOARD_JS__", _asset_text("dashboard.js"))
        .replace("__NOTIFICATION_LIMIT__", str(notification_limit))
    )
