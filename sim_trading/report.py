from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sim_trading.ledger import LedgerService
from sim_trading.models import decimal_to_money, decimal_to_str, to_decimal
from sim_trading.storage import read_csv_rows


def _trade_rows_for_day(service: LedgerService, report_day: date) -> list[dict[str, str]]:
    rows = read_csv_rows(service.paths.trades)
    return [row for row in rows if datetime.fromisoformat(row["timestamp"]).date() == report_day]


def _equity_rows_until_day(service: LedgerService, report_day: date) -> list[dict[str, str]]:
    cutoff = service.normalization_cutoff()
    rows = read_csv_rows(service.paths.equity_curve)
    filtered: list[dict[str, str]] = []
    for row in rows:
        row_dt = datetime.fromisoformat(row["timestamp"])
        if row_dt.date() > report_day:
            continue
        if cutoff is not None and report_day >= cutoff.date() and row_dt < cutoff:
            continue
        filtered.append(row)
    return filtered


def _equity_rows_for_day(service: LedgerService, report_day: date) -> list[dict[str, str]]:
    cutoff = service.normalization_cutoff()
    rows = read_csv_rows(service.paths.equity_curve)
    filtered: list[dict[str, str]] = []
    for row in rows:
        row_dt = datetime.fromisoformat(row["timestamp"])
        if row_dt.date() != report_day:
            continue
        if cutoff is not None and row_dt < cutoff:
            continue
        filtered.append(row)
    return filtered


def generate_daily_report(
    *,
    state_dir: Path | str,
    report_day: date,
    output_path: Path | str | None = None,
) -> Path:
    service = LedgerService(state_dir)
    equity_rows = _equity_rows_for_day(service, report_day)
    if not equity_rows:
        raise ValueError(f"no equity snapshots available for {report_day.isoformat()}")

    upto_day = _equity_rows_until_day(service, report_day)
    opening = equity_rows[0]
    closing = equity_rows[-1]
    opening_nav = to_decimal(opening["nav"])
    closing_nav = to_decimal(closing["nav"])
    pnl = closing_nav - opening_nav
    day_return_pct = (pnl / opening_nav) if opening_nav > 0 else Decimal("0")
    max_drawdown = min((to_decimal(row["drawdown_pct"]) for row in upto_day), default=Decimal("0"))

    trade_rows = _trade_rows_for_day(service, report_day)
    closed_rows = [row for row in trade_rows if to_decimal(row["realized_pnl"]) != 0]
    winners = [to_decimal(row["realized_pnl"]) for row in closed_rows if to_decimal(row["realized_pnl"]) > 0]
    losers = [to_decimal(row["realized_pnl"]) for row in closed_rows if to_decimal(row["realized_pnl"]) < 0]
    gross_profit = sum(winners, Decimal("0"))
    gross_loss = sum(losers, Decimal("0"))
    win_rate = (Decimal(len(winners)) / Decimal(len(closed_rows))) if closed_rows else Decimal("0")
    avg_winner = (gross_profit / Decimal(len(winners))) if winners else Decimal("0")
    avg_loser = (gross_loss / Decimal(len(losers))) if losers else Decimal("0")

    latest_snapshot = service.build_snapshot(
        timestamp=closing["timestamp"],
        price_overrides=None,
    )
    positions = service.load_positions()
    position_mode = service.position_mode_status()

    lines = [
        f"# Daily Sim-Trading Report - {report_day.isoformat()}",
        "",
        "## Portfolio",
        f"- Opening NAV: {decimal_to_money(opening_nav)}",
        f"- Closing NAV: {decimal_to_money(closing_nav)}",
        f"- Day PnL: {decimal_to_money(pnl)} ({day_return_pct:.2%})",
        f"- Current Drawdown: {to_decimal(closing['drawdown_pct']):.2%}",
        f"- Max Drawdown To Date: {max_drawdown:.2%}",
        f"- Cash: {decimal_to_money(latest_snapshot.cash_balance)}",
        f"- Market Value: {decimal_to_money(latest_snapshot.positions_market_value)}",
        f"- Position Mode: {position_mode['mode']}",
        "",
        "## Trade Stats",
        f"- Trades Today: {len(trade_rows)}",
        f"- Closed Trades Today: {len(closed_rows)}",
        f"- Win Rate: {win_rate:.2%}",
        f"- Gross Profit: {decimal_to_money(gross_profit)}",
        f"- Gross Loss: {decimal_to_money(gross_loss)}",
        f"- Avg Winner: {decimal_to_money(avg_winner)}",
        f"- Avg Loser: {decimal_to_money(avg_loser)}",
    ]
    if position_mode["is_normalized"]:
        lines.insert(11, f"- Normalized At: {position_mode['normalized_at'] or 'unknown'}")
    elif position_mode["requires_normalization"]:
        lines.insert(11, "- Normalization Pending: yes")

    if closed_rows:
        best_trade = max(closed_rows, key=lambda row: to_decimal(row["realized_pnl"]))
        worst_trade = min(closed_rows, key=lambda row: to_decimal(row["realized_pnl"]))
        lines.extend(
            [
                f"- Best Trade: {best_trade['symbol']} {best_trade['side']} {decimal_to_money(best_trade['realized_pnl'])}",
                f"- Worst Trade: {worst_trade['symbol']} {worst_trade['side']} {decimal_to_money(worst_trade['realized_pnl'])}",
            ]
        )
    else:
        lines.append("- Best/Worst Trade: no realized exits today")

    lines.extend(["", "## Open Positions"])
    if positions:
        for symbol in sorted(positions):
            position = positions[symbol]
            mark = latest_snapshot.marks.get(symbol, position.last_price)
            lines.append(
                "- "
                + f"{symbol}: qty {decimal_to_str(position.quantity)}, avg {decimal_to_money(position.average_entry_price)}, "
                + f"mark {decimal_to_money(mark)}, mv {decimal_to_money(position.market_value(mark))}, "
                + f"uPnL {decimal_to_money(position.unrealized_pnl(mark))}, "
                + f"stop {decimal_to_money(position.stop_loss) if position.stop_loss is not None else 'n/a'}"
            )
    else:
        lines.append("- No open positions")

    lines.extend(["", "## Risk Alerts"])
    if latest_snapshot.breached_stop_losses:
        for symbol in latest_snapshot.breached_stop_losses:
            lines.append(f"- Stop-loss breached: {symbol}")
    else:
        lines.append("- No stop-loss breaches")

    destination = Path(output_path) if output_path is not None else service.paths.reports_dir / f"{report_day.isoformat()}.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
