from __future__ import annotations

import csv
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TRADE_HEADERS = [
    "trade_id",
    "timestamp",
    "symbol",
    "side",
    "quantity",
    "price",
    "notional",
    "fee",
    "strategy",
    "note",
    "stop_loss",
    "realized_pnl",
    "cash_after",
    "position_qty_after",
    "nav_after",
]

EQUITY_HEADERS = [
    "timestamp",
    "cash_balance",
    "positions_market_value",
    "nav",
    "realized_pnl_total",
    "unrealized_pnl_total",
    "drawdown_pct",
    "breached_stop_losses",
    "marks_json",
]

ORDER_EVENT_STATUSES = {"pending", "partial", "filled", "canceled", "rejected"}


@dataclass(frozen=True)
class StoragePaths:
    root: Path

    @property
    def account(self) -> Path:
        return self.root / "account.json"

    @property
    def config(self) -> Path:
        return self.root / "config.json"

    @property
    def positions(self) -> Path:
        return self.root / "positions.json"

    @property
    def market_prices(self) -> Path:
        return self.root / "market_prices.json"

    @property
    def market_feed(self) -> Path:
        return self.root / "market_feed.jsonl"

    @property
    def universe_all(self) -> Path:
        return self.root / "universe_all.json"

    @property
    def universe_filtered(self) -> Path:
        return self.root / "universe_filtered.json"

    @property
    def universe_top120(self) -> Path:
        return self.root / "universe_top120.json"

    @property
    def universe_top30(self) -> Path:
        return self.root / "universe_top30.json"

    @property
    def universe_runs(self) -> Path:
        return self.root / "universe_runs.jsonl"

    @property
    def signal_runs(self) -> Path:
        return self.root / "signal_runs.jsonl"

    @property
    def ds_requests(self) -> Path:
        return self.root / "ds_requests.jsonl"

    @property
    def ds_decisions(self) -> Path:
        return self.root / "ds_decisions.jsonl"

    @property
    def ds_rejections(self) -> Path:
        return self.root / "ds_rejections.jsonl"

    @property
    def ds_approvals(self) -> Path:
        return self.root / "ds_approvals.jsonl"

    @property
    def order_events(self) -> Path:
        return self.root / "order_events.jsonl"

    @property
    def execution_runs(self) -> Path:
        return self.root / "execution_runs.jsonl"

    @property
    def risk_state(self) -> Path:
        return self.root / "risk_state.json"

    @property
    def risk_events(self) -> Path:
        return self.root / "risk_events.jsonl"

    @property
    def validation_runs(self) -> Path:
        return self.root / "validation_runs.jsonl"

    @property
    def webhook_nonces(self) -> Path:
        return self.root / "webhook_nonces.json"

    @property
    def normalization_audit(self) -> Path:
        return self.root / "position_normalizations.jsonl"

    @property
    def trades(self) -> Path:
        return self.root / "trades.csv"

    @property
    def equity_curve(self) -> Path:
        return self.root / "equity_curve.csv"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def strategies_root(self) -> Path:
        return self.root / "strategies"

    def ensure_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.strategies_root.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
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


def ensure_json(path: Path, payload: Any) -> bool:
    if path.exists():
        return False
    write_json(path, payload)
    return True


def ensure_csv(path: Path, headers: list[str]) -> bool:
    if path.exists():
        return False
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
    return True


def append_csv_row(path: Path, headers: list[str], row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writerow(row)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []
    rows: list[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def read_last_jsonl(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()
    for raw_line in reversed(lines):
        line = raw_line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None
