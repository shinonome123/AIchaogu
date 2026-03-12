from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from sim_trading.ds_operator import (
    DeepSeekDecisionError,
    approve_latest_deepseek_decision,
    build_signal_entry_from_ds_decision,
    load_ds_decision_by_id,
    load_latest_active_ds_approval,
    load_latest_ds_decision,
    mark_latest_approval_consumed,
    run_deepseek_shadow,
)
from sim_trading.execution import SimulationExecutor, build_risk_status, set_kill_switch
from sim_trading.ledger import LedgerService
from sim_trading.market import fetch_market_snapshot, resolve_market_symbols, run_signal_snapshot
from sim_trading.models import decimal_to_money, decimal_to_str, to_decimal
from sim_trading.notifier import (
    auto_reporting_enabled,
    default_report_log_path,
    human_summary,
    notify_task,
)
from sim_trading.ops import build_health_snapshot, build_status_snapshot, emit_status_report, format_health_lines
from sim_trading.security import (
    DEFAULT_DASHBOARD_BASIC_PASS_ENV,
    DEFAULT_DASHBOARD_BASIC_USER_ENV,
    DEFAULT_DASHBOARD_BEARER_ENV,
    DEFAULT_WEBHOOK_REPLAY_TTL_ENV,
    DashboardAuthConfig,
    generate_secret,
    redact_secret,
    upsert_env_file,
)
from sim_trading.strategy_tracks import (
    build_strategy_signal_entry,
    build_strategy_comparison,
    format_strategy_compare_table,
    load_strategy_selection,
    run_strategy_track,
    set_strategy_selection,
)
from sim_trading.report import generate_daily_report
from sim_trading.servers import (
    DashboardServerConfig,
    WebhookServerConfig,
    create_dashboard_server,
    create_webhook_server,
)
from sim_trading.universe import refresh_universe
from sim_trading.validation import StrategyValidator


def parse_prices(items: list[str] | None) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"invalid --price '{item}', expected SYMBOL=PRICE")
        symbol, raw_price = item.split("=", 1)
        prices[symbol] = to_decimal(raw_price)
    return prices


def resolve_report_log(args: argparse.Namespace) -> Path:
    if getattr(args, "report_log", None):
        return Path(args.report_log).resolve()
    return default_report_log_path(args.state_dir)


def _warn_auto_report_failure(exc: Exception) -> None:
    print(f"warning: auto-report failed: {exc}", file=sys.stderr)


def maybe_auto_report(
    args: argparse.Namespace,
    *,
    task: str,
    status: str,
    did_what: str,
    risk_impact: str,
    next_step: str,
    source: str,
) -> None:
    if not auto_reporting_enabled():
        return
    try:
        result = notify_task(
            report_log=resolve_report_log(args),
            task=task,
            status=status,
            did_what=did_what,
            risk_impact=risk_impact,
            next_step=next_step,
            source=source,
            hook_command=getattr(args, "hook_command", None),
        )
    except Exception as exc:
        _warn_auto_report_failure(exc)
        return

    if result.hook_returncode not in {None, 0}:
        _warn_auto_report_failure(RuntimeError(f"hook exited with {result.hook_returncode}"))


def summarize_snapshot_status(snapshot: dict[str, str | list[str] | int | None]) -> tuple[str, str, str]:
    breached = snapshot["breached_stop_losses"]
    drawdown = to_decimal(snapshot["drawdown_pct"])
    if bool(snapshot.get("position_requires_normalization")) and not breached and drawdown > Decimal("-0.05"):
        risk = "Legacy synthetic seed-unit positions still need normalization before NAV is comparable to market marks."
        return "watch", risk, "Run normalize-positions after refreshing market prices."
    if breached:
        risk = f"Stop-loss breached for {', '.join(breached)}. Portfolio drawdown is {drawdown:.2%}."
        return "alert", risk, "Review breached stops and reduce or close exposure as needed."
    if drawdown <= Decimal("-0.05"):
        risk = f"Portfolio drawdown is {drawdown:.2%}; exposure should be reviewed closely."
        return "watch", risk, "Refresh marks, review sizing, and continue tighter monitoring."
    if bool(snapshot.get("position_mode_is_normalized")):
        return "ok", "Portfolio is in normalized seed-notional mode and within current drawdown and stop-loss limits.", "Continue scheduled monitoring."
    return "ok", "Portfolio is within current drawdown and stop-loss limits.", "Continue scheduled monitoring."


def resolve_dashboard_auth(args: argparse.Namespace) -> DashboardAuthConfig:
    bearer_token = os.getenv(args.dashboard_bearer_env, "").strip() or None
    basic_username = os.getenv(args.dashboard_basic_user_env, "").strip() or None
    basic_password = os.getenv(args.dashboard_basic_pass_env, "").strip() or None
    return DashboardAuthConfig(
        bearer_token=bearer_token,
        basic_username=basic_username,
        basic_password=basic_password,
        bearer_env=args.dashboard_bearer_env,
        basic_user_env=args.dashboard_basic_user_env,
        basic_pass_env=args.dashboard_basic_pass_env,
    )


def resolve_webhook_replay_ttl(args: argparse.Namespace) -> int:
    configured = getattr(args, "replay_ttl_seconds", None)
    if configured is not None:
        return max(0, configured)
    env_value = os.getenv(DEFAULT_WEBHOOK_REPLAY_TTL_ENV, "").strip()
    if not env_value:
        return 0
    return max(0, int(env_value))


def cmd_init(args: argparse.Namespace) -> int:
    service = LedgerService(args.state_dir)
    created = service.initialize_from_seed(args.seed_file)
    if created:
        print("Initialized state:")
        for path in created:
            print(f"- {path}")
        maybe_auto_report(
            args,
            task="state-init",
            status="initialized",
            did_what=f"Initialized sim-trading state under {Path(args.state_dir).resolve()}.",
            risk_impact="Bootstrap only. No portfolio exposure changed.",
            next_step="Record trades, persist snapshots, or start the ops dashboard.",
            source="cli.init",
        )
    else:
        print(f"State already initialized at {args.state_dir}")
        maybe_auto_report(
            args,
            task="state-init",
            status="no_change",
            did_what=f"Checked state bootstrap at {Path(args.state_dir).resolve()} and found it already initialized.",
            risk_impact="No changes were applied to portfolio state.",
            next_step="Proceed with trading, status reporting, or dashboard startup.",
            source="cli.init",
        )
    return 0


def cmd_record_trade(args: argparse.Namespace) -> int:
    service = LedgerService(args.state_dir)
    result = service.record_trade(
        symbol=args.symbol,
        side=args.side,
        quantity=to_decimal(args.quantity),
        price=to_decimal(args.price),
        fee=to_decimal(args.fee),
        timestamp=args.timestamp,
        strategy=args.strategy,
        note=args.note,
        stop_loss=to_decimal(args.stop_loss) if args.stop_loss is not None else None,
    )
    print(
        f"{result.trade_id} {result.side.upper()} {result.symbol} "
        f"qty={decimal_to_str(result.quantity)} price={decimal_to_money(result.price)} "
        f"realized={decimal_to_money(result.realized_pnl)} nav_after={decimal_to_money(result.nav_after)}"
    )
    trade_status = "watch" if result.realized_pnl < 0 else "ok"
    risk_impact = (
        f"Trade changed exposure and left NAV at {decimal_to_money(result.nav_after)}. "
        + (
            f"Realized loss {decimal_to_money(result.realized_pnl)}; confirm loss limits and stops."
            if result.realized_pnl < 0
            else "No realized loss escalation from this fill."
        )
    )
    maybe_auto_report(
        args,
        task="record-trade",
        status=trade_status,
        did_what=(
            f"Recorded {result.side.upper()} {result.symbol} qty={decimal_to_str(result.quantity)} "
            + f"at {decimal_to_money(result.price)}."
        ),
        risk_impact=risk_impact,
        next_step="Refresh the dashboard or emit a status report to confirm updated exposure.",
        source="cli.record-trade",
    )
    return 0


def cmd_normalize_positions(args: argparse.Namespace) -> int:
    service = LedgerService(args.state_dir)
    result = service.normalize_seed_positions(
        timestamp=args.timestamp,
        price_overrides=parse_prices(args.price),
        source_note=args.source_note,
    )
    mode = service.position_mode_status()
    print(
        f"{result['timestamp']} normalized_positions={len(result['normalized_positions'])} "
        + f"mode={mode['mode']} audit={result['audit_path']}"
    )
    for row in result["normalized_positions"]:
        print(
            f"- {row['symbol']} carrying_notional={row['carrying_notional']} "
            + f"qty {row['previous_quantity']} -> {row['normalized_quantity']} "
            + f"mark {row['normalized_average_entry_price']} ({row['reference_type']})"
        )
    print(
        "before_nav="
        + decimal_to_money(result["before_snapshot"]["nav"])
        + " after_nav="
        + decimal_to_money(result["after_snapshot"]["nav"])
    )
    maybe_auto_report(
        args,
        task="position-normalization",
        status="ok",
        did_what=(
            f"Normalized {len(result['normalized_positions'])} synthetic seed positions into "
            + f"carrying-notional market-based quantities at {result['timestamp']}."
        ),
        risk_impact=(
            "Simulation-only migration. Open-position unrealized PnL was reset from the normalization mark; "
            + f"audit trail written to {result['audit_path']}."
        ),
        next_step="Refresh the dashboard or emit a status report to confirm normalized mode and charts.",
        source="cli.normalize-positions",
    )
    return 0


def cmd_snapshot(args: argparse.Namespace, *, persist: bool) -> int:
    service = LedgerService(args.state_dir)
    snapshot = service.snapshot(
        timestamp=args.timestamp,
        persist=persist,
        price_overrides=parse_prices(args.price),
    )
    print("\n".join(service.status_lines(snapshot)))

    if persist:
        snapshot_data = build_status_snapshot(state_dir=args.state_dir, timestamp=snapshot.timestamp)
        status, risk_impact, next_step = summarize_snapshot_status(snapshot_data)
        maybe_auto_report(
            args,
            task="snapshot",
            status=status,
            did_what=(
                f"Persisted marked-to-market snapshot at {snapshot.timestamp} with NAV "
                + f"{decimal_to_money(snapshot.nav)} across {snapshot_data['position_count']} positions."
            ),
            risk_impact=risk_impact,
            next_step=next_step,
            source="cli.snapshot",
        )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    report_day = date.fromisoformat(args.date) if args.date else date.today()
    destination = generate_daily_report(
        state_dir=args.state_dir,
        report_day=report_day,
        output_path=args.output,
    )
    print(destination)
    maybe_auto_report(
        args,
        task="daily-report",
        status="ok",
        did_what=f"Generated markdown report for {report_day.isoformat()} at {destination}.",
        risk_impact="Reporting only. Portfolio state was not changed.",
        next_step="Share the report and keep hourly status reporting running.",
        source="cli.report",
    )
    return 0


def cmd_notify_task(args: argparse.Namespace) -> int:
    result = notify_task(
        report_log=resolve_report_log(args),
        task=args.task,
        status=args.status,
        did_what=args.did_what,
        risk_impact=args.risk,
        next_step=args.next,
        source=args.source,
        hook_command=args.hook_command,
    )
    print(human_summary(result))
    return 0


def cmd_emit_status_report(args: argparse.Namespace) -> int:
    result = emit_status_report(
        state_dir=args.state_dir,
        report_log=resolve_report_log(args),
        source=args.source,
        task=args.task,
        hook_command=args.hook_command,
        timestamp=args.timestamp,
    )
    print(human_summary(result))
    return 0


def cmd_serve_webhook(args: argparse.Namespace) -> int:
    replay_ttl_seconds = resolve_webhook_replay_ttl(args)
    with create_webhook_server(
        host=args.host,
        port=args.port,
        config=WebhookServerConfig(
            state_dir=Path(args.state_dir).resolve(),
            report_log=resolve_report_log(args),
            token_env=args.token_env,
            hook_command=args.hook_command,
            replay_ttl_seconds=replay_ttl_seconds,
        ),
    ) as httpd:
        maybe_auto_report(
            args,
            task="webhook-server",
            status="running",
            did_what=f"Started webhook listener on http://{args.host}:{args.port}/task-done.",
            risk_impact=(
                f"Requests require the shared token from env {args.token_env}."
                + (
                    f" Replay protection is enabled with TTL {replay_ttl_seconds}s."
                    if replay_ttl_seconds > 0
                    else " Replay protection is disabled."
                )
            ),
            next_step="POST task completion payloads to /task-done to populate the report log.",
            source="cli.serve-webhook",
        )
        if replay_ttl_seconds > 0:
            print(
                f"Webhook replay protection enabled: TTL {replay_ttl_seconds}s, nonce store "
                + f"{LedgerService(args.state_dir).paths.webhook_nonces}",
                file=sys.stderr,
            )
        print(f"Serving webhook on http://{args.host}:{args.port}/task-done")
        httpd.serve_forever()
    return 0


def cmd_serve_dashboard(args: argparse.Namespace) -> int:
    auth = resolve_dashboard_auth(args)
    if not auth.is_configured():
        print(
            "warning: dashboard auth is disabled for / and /api/status; "
            + f"set {args.dashboard_bearer_env} or {args.dashboard_basic_user_env}/{args.dashboard_basic_pass_env}",
            file=sys.stderr,
        )
    else:
        print(f"Dashboard auth enabled via {', '.join(auth.enabled_methods())}", file=sys.stderr)
    with create_dashboard_server(
        host=args.host,
        port=args.port,
        config=DashboardServerConfig(
            state_dir=Path(args.state_dir).resolve(),
            report_log=resolve_report_log(args),
            notification_limit=args.limit,
            auth=auth,
            health_max_report_age_seconds=args.health_max_report_age_seconds,
        ),
    ) as httpd:
        maybe_auto_report(
            args,
            task="dashboard-server",
            status="running",
            did_what=f"Started dashboard on http://{args.host}:{args.port}/.",
            risk_impact=(
                "Dashboard is read-only."
                + (
                    f" Auth enabled via {', '.join(auth.enabled_methods())}."
                    if auth.is_configured()
                    else " Auth is disabled; restrict network exposure."
                )
            ),
            next_step="Open the panel locally or expose it later with FRP/reverse proxying.",
            source="cli.serve-dashboard",
        )
        print(f"Serving dashboard on http://{args.host}:{args.port}/")
        httpd.serve_forever()
    return 0


def cmd_rotate_tokens(args: argparse.Namespace) -> int:
    webhook_token = generate_secret()
    dashboard_bearer = generate_secret()
    dashboard_basic_password = generate_secret()
    updates = {
        args.webhook_token_env: webhook_token,
        args.dashboard_bearer_env: dashboard_bearer,
        args.dashboard_basic_user_env: args.dashboard_basic_user,
        args.dashboard_basic_pass_env: dashboard_basic_password,
        DEFAULT_WEBHOOK_REPLAY_TTL_ENV: str(args.replay_ttl_seconds),
    }
    target = Path(args.ops_env).resolve()
    upsert_env_file(target, updates)
    visible = lambda value: value if args.show else redact_secret(value)
    print(f"Wrote rotated ops secrets to {target}")
    print(f"- {args.webhook_token_env}={visible(webhook_token)}")
    print(f"- {args.dashboard_bearer_env}={visible(dashboard_bearer)}")
    print(f"- {args.dashboard_basic_user_env}={args.dashboard_basic_user}")
    print(f"- {args.dashboard_basic_pass_env}={visible(dashboard_basic_password)}")
    print(f"- {DEFAULT_WEBHOOK_REPLAY_TTL_ENV}={args.replay_ttl_seconds}")
    if not args.show:
        print("Use --show to print full secrets.")
    return 0


def cmd_health_check(args: argparse.Namespace) -> int:
    snapshot = build_health_snapshot(
        state_dir=args.state_dir,
        report_log=resolve_report_log(args),
        max_report_age_seconds=args.max_report_age_seconds,
        dashboard_pid_file=args.dashboard_pid_file,
        webhook_pid_file=args.webhook_pid_file,
        dashboard_health_url=args.dashboard_health_url,
        webhook_host=args.webhook_host,
        webhook_port=args.webhook_port,
        timeout_seconds=args.timeout_seconds,
    )
    if args.output_json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print("\n".join(format_health_lines(snapshot)))
    return 0 if snapshot["ok"] else 1


def cmd_fetch_market(args: argparse.Namespace) -> int:
    symbols = resolve_market_symbols(args.state_dir, args.symbol)
    append_feed = not bool(getattr(args, "prices_only", False))
    result = fetch_market_snapshot(
        state_dir=args.state_dir,
        symbols=symbols,
        source=args.source,
        api_root=args.api_root,
        timestamp=args.timestamp,
        timeout_seconds=args.timeout_seconds,
        append_feed=append_feed,
    )
    mode = "prices+feed" if append_feed else "prices-only"
    print(f"{result.entry['timestamp']} source={result.entry['source']} symbols={len(symbols)} mode={mode}")
    prices = result.entry["prices"]
    assert isinstance(prices, dict)
    for symbol in symbols:
        item = prices[symbol]
        assert isinstance(item, dict)
        print(f"- {symbol} price={item['price']}")
    return 0


def cmd_universe_refresh(args: argparse.Namespace) -> int:
    result = refresh_universe(
        state_dir=args.state_dir,
        source=args.source,
        api_root=args.api_root,
        timestamp=args.timestamp,
        timeout_seconds=args.timeout_seconds,
        top_limit=args.top_limit,
        ds_limit=args.ds_limit,
        min_listing_age_days=args.min_listing_age_days,
        min_quote_volume=to_decimal(args.min_quote_volume),
        min_trade_count=args.min_trade_count,
        max_spread_pct=to_decimal(args.max_spread_pct),
    )
    entry = result.entry
    print(
        f"{entry['timestamp']} all={entry['counts']['all']} filtered={entry['counts']['filtered']} "
        + f"top120={entry['counts']['top120']} top30={entry['counts']['top30']}"
    )
    print(f"ranking_rule={entry['ranking_rule']}")
    print("top120_sample=" + ", ".join(result.universe_top120["symbols"][:10]))
    print("top30_sample=" + ", ".join(result.universe_top30["symbols"][:10]))
    maybe_auto_report(
        args,
        task="universe-refresh",
        status="ok",
        did_what=(
            f"Refreshed Binance spot USDT universe with {entry['counts']['filtered']} filtered symbols and "
            + f"published Top 120 / Top 30 artifacts under {Path(args.state_dir).resolve()}."
        ),
        risk_impact=(
            "Universe selection only. No real trading path exists, and the shared feed remains simulation-only. "
            + f"Ranking rule: {entry['ranking_rule']}"
        ),
        next_step="Run strategy-run for baseline and DS tracks against the refreshed shortlist.",
        source="cli.universe-refresh",
    )
    return 0


def cmd_run_signals(args: argparse.Namespace) -> int:
    result = run_signal_snapshot(
        state_dir=args.state_dir,
        source=args.source,
        lookback_points=args.lookback_points,
        timestamp=args.timestamp,
    )
    entry = result.entry
    print(f"{entry['timestamp']} {entry['summary']}")
    for signal in entry["signals"]:
        print(
            f"- {signal['symbol']} signal={signal['signal']} obs={signal['observations']} "
            + f"momentum={signal['momentum']} ema_slope={signal['ema_slope']}"
        )

    if args.notify:
        notify_result = notify_task(
            report_log=resolve_report_log(args),
            task=args.task,
            status=str(entry["status"]),
            did_what=(
                f"Ran signal snapshot across {entry['signal_count']} symbols using market feed "
                + f"at {entry['market_timestamp']}."
            ),
            risk_impact=(
                f"{entry['summary']}. Review suggested targets before any manual simulated execution."
            ),
            next_step="Inspect the dashboard signal panel and decide whether to record simulated trades.",
            source=args.notify_source,
            hook_command=args.hook_command,
            timestamp=str(entry["timestamp"]),
        )
        print(human_summary(notify_result))
    return 0


def cmd_strategy_run(args: argparse.Namespace) -> int:
    result = run_strategy_track(
        args.state_dir,
        strategy=args.strategy,
        timestamp=args.timestamp,
        lookback_points=args.lookback_points,
        source=args.source,
    )
    print(
        f"{args.strategy} status={result['status']} nav={result['nav']} "
        + f"signal={result.get('signal_summary', 'n/a')}"
    )
    if result.get("decision_id"):
        print(f"decision_id={result['decision_id']}")
    execution = result.get("execution")
    if isinstance(execution, dict):
        print(
            f"execution_id={execution['execution_id']} fills={execution['fills_count']} "
            + f"rejected={execution['rejected_orders']} nav_after={execution['nav_after']}"
        )
    else:
        print(f"reason={result['reason']}")
    maybe_auto_report(
        args,
        task=f"strategy-run:{args.strategy}",
        status="ok" if execution else "watch",
        did_what=(
            f"Ran strategy track {args.strategy} with isolated state under {result['state_dir']}."
        ),
        risk_impact=(
            "Each strategy ledger remains isolated with shared market feed assumptions only. "
            + (
                f"Execution result: {execution['summary']}."
                if isinstance(execution, dict)
                else f"No execution completed: {result['reason']}."
            )
        ),
        next_step="Use strategy-compare or the dashboard comparison panel to review cross-strategy drift.",
        source="cli.strategy-run",
    )
    return 0


def cmd_strategy_compare(args: argparse.Namespace) -> int:
    payload = build_strategy_comparison(
        args.state_dir,
        timestamp=args.timestamp,
        ensure_initialized=True,
    )
    if not args.output_json:
        print(format_strategy_compare_table(payload))
        print()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_ds_shadow_run(args: argparse.Namespace) -> int:
    result = run_deepseek_shadow(
        state_dir=args.state_dir,
        source=args.source,
        timestamp=args.timestamp,
    )
    if result.decision_entry is not None:
        entry = result.decision_entry
        print(f"{entry['timestamp']} {entry['summary']}")
        for decision in entry["payload"]["decisions"]:
            print(
                f"- {decision['symbol']} action={decision['action']} target={decision['target_weight']} "
                + f"confidence={decision['confidence']}"
            )
        adjustments = entry.get("execution_preview", {}).get("adjustments", [])
        if isinstance(adjustments, list):
            for adjustment in adjustments:
                print(f"  adjustment={adjustment}")

        if args.notify:
            notify_result = notify_task(
                report_log=resolve_report_log(args),
                task=args.task,
                status="ok",
                did_what=(
                    f"Recorded DeepSeek shadow decision {entry['decision_id']} with "
                    + f"{entry['decision_count']} structured suggestions."
                ),
                risk_impact=(
                    f"{entry['summary']}. "
                    + (
                        f"Execution preview adjustments: {', '.join(adjustments)}."
                        if adjustments
                        else "No execution preview clipping was required."
                    )
                ),
                next_step="Review the DS panel and approve the latest plan if you want one simulated execution cycle.",
                source=args.notify_source,
                hook_command=args.hook_command,
                timestamp=str(entry["timestamp"]),
            )
            print(human_summary(notify_result))
        return 0

    rejection = result.rejection_entry or {}
    print(f"{result.request_entry['timestamp']} status={result.status} reason={result.reason}")
    if result.status == "noop":
        return 0
    if args.notify:
        notify_result = notify_task(
            report_log=resolve_report_log(args),
            task=args.task,
            status="watch",
            did_what="DeepSeek shadow run did not produce an executable structured plan.",
            risk_impact=str(rejection.get("reason", result.reason)),
            next_step="Inspect ds_rejections.jsonl and fix the DS config, context, or schema prompt before retrying.",
            source=args.notify_source,
            hook_command=args.hook_command,
            timestamp=str(rejection.get("timestamp", result.request_entry["timestamp"])),
        )
        print(human_summary(notify_result))
    return 1


def cmd_ds_approve_latest(args: argparse.Namespace) -> int:
    approval_entry = approve_latest_deepseek_decision(
        args.state_dir,
        source=args.source,
        timestamp=args.timestamp,
    )
    print(
        f"{approval_entry['timestamp']} approval_id={approval_entry['approval_id']} "
        + f"decision_id={approval_entry['decision_id']}"
    )
    latest_decision = load_latest_ds_decision(args.state_dir)
    if args.notify and latest_decision is not None:
        notify_result = notify_task(
            report_log=resolve_report_log(args),
            task=args.task,
            status="ok",
            did_what=(
                f"Approved DeepSeek plan {approval_entry['decision_id']} for the next "
                + "simulated execution cycle."
            ),
            risk_impact=str(approval_entry.get("decision_summary", "")),
            next_step="Run execute-sim --decision-source ds-approved when you want to consume this approval.",
            source=args.notify_source,
            hook_command=args.hook_command,
            timestamp=str(approval_entry["timestamp"]),
        )
        print(human_summary(notify_result))
    return 0


def _print_execution_summary(entry: dict[str, object]) -> None:
    print(f"{entry['timestamp']} {entry['summary']}")
    for order in entry.get("orders", []):
        if not isinstance(order, dict):
            continue
        reason = f" reason={order['reason']}" if order.get("reason") else ""
        print(
            f"- {order['symbol']} {str(order['side']).upper()} status={order['status']} "
            + f"req={order['requested_quantity']} filled={order.get('filled_quantity_total', '0')} "
            + f"remaining={order.get('remaining_quantity', '0')}{reason}"
        )


def cmd_execute_sim(args: argparse.Namespace) -> int:
    executor = SimulationExecutor(args.state_dir)
    signal_entry = None
    if args.decision_source == "ds-approved":
        approval_entry = load_latest_active_ds_approval(args.state_dir)
        if approval_entry is None:
            raise FileNotFoundError("no active DS approval is available; run ds-approve-latest first")
        decision_id = str(approval_entry.get("decision_id", "")).strip()
        decision_entry = load_ds_decision_by_id(args.state_dir, decision_id)
        if decision_entry is None:
            raise FileNotFoundError(f"approved DS decision not found: {decision_id}")
        try:
            signal_entry = build_signal_entry_from_ds_decision(
                state_dir=args.state_dir,
                decision_entry=decision_entry,
                source=args.source,
                timestamp=args.timestamp,
            )
        except DeepSeekDecisionError as exc:
            raise RuntimeError(f"approved DS decision could not be converted: {exc}") from exc
    elif args.decision_source == "strategy-selected":
        selection = load_strategy_selection(args.state_dir)
        selected = selection.get("selected_strategy")
        if not selection.get("enabled") or not selected:
            raise RuntimeError("strategy-selected execution is not enabled; run strategy-selection set --strategy <name>")
        signal_entry = build_strategy_signal_entry(
            args.state_dir,
            strategy=str(selected),
            timestamp=args.timestamp,
            lookback_points=args.lookback_points,
            source=args.source,
        )

    result = executor.execute_cycle(
        timestamp=args.timestamp,
        signal_run_entry=signal_entry,
        source=args.source,
        lookback_points=args.lookback_points,
        price_overrides=parse_prices(args.price),
    )
    entry = result.entry
    if args.decision_source == "ds-approved":
        mark_latest_approval_consumed(
            args.state_dir,
            execution_id=str(entry["execution_id"]),
            source=args.source,
            timestamp=str(entry["timestamp"]),
        )
    _print_execution_summary(entry)

    rejection_count = int(entry.get("rejected_orders", 0))
    risk_status = entry.get("risk_status", {})
    blocked = isinstance(risk_status, dict) and bool(risk_status.get("blocked_new_orders"))
    status = "alert" if rejection_count else ("watch" if blocked else "ok")
    maybe_auto_report(
        args,
        task="execute-sim",
        status=status,
        did_what=(
            f"Ran one simulation execution cycle from {entry.get('decision_source', 'signals')} with {entry['fills_count']} fills, "
            + f"{entry['partial_orders']} partial orders, {entry['canceled_orders']} cancellations, and "
            + f"{entry['rejected_orders']} rejections."
        ),
        risk_impact=(
            f"NAV {decimal_to_money(entry['nav_before'])} -> {decimal_to_money(entry['nav_after'])}; "
            + f"fees {decimal_to_money(entry['fees_total'])}, slippage {decimal_to_money(entry['slippage_total'])}."
            + (
                " Risk gates blocked new buy orders: " + "; ".join(risk_status.get("blocked_reasons", []))
                if blocked and isinstance(risk_status, dict)
                else ""
            )
        ),
        next_step=(
            "Inspect risk-status and latest execution summary on the dashboard before the next cycle."
            if rejection_count or blocked
            else "Keep market fetch, signals, and the next execution cycle on schedule."
        ),
        source="cli.execute-sim",
    )
    if (rejection_count or blocked) and args.notify:
        notify_result = notify_task(
            report_log=resolve_report_log(args),
            task="risk-rejection",
            status="alert",
            did_what=(
                f"Execution cycle {entry['execution_id']} recorded {rejection_count} rejected orders and "
                + f"{entry['canceled_orders']} cancellations."
            ),
            risk_impact=(
                "; ".join(risk_status.get("blocked_reasons", []))
                if isinstance(risk_status, dict) and risk_status.get("blocked_reasons")
                else "See state/risk_events.jsonl for detailed execution-time rejections."
            ),
            next_step="Clear the blocker or reduce exposure before submitting the next simulated buy order.",
            source="cli.execute-sim",
            hook_command=args.hook_command,
            timestamp=str(entry["timestamp"]),
        )
        print(human_summary(notify_result))
    return 0


def cmd_strategy_selection(args: argparse.Namespace) -> int:
    if args.action == "status":
        selection = load_strategy_selection(args.state_dir)
    elif args.action == "set":
        if not args.strategy:
            raise ValueError("--strategy is required when action is 'set'")
        selection = set_strategy_selection(
            args.state_dir,
            strategy=args.strategy,
            enabled=True,
        )
    else:
        selection = set_strategy_selection(
            args.state_dir,
            strategy=None,
            enabled=False,
        )
    print(json.dumps(selection, indent=2, sort_keys=True))
    return 0


def cmd_risk_status(args: argparse.Namespace) -> int:
    if args.kill_switch is not None:
        enabled = args.kill_switch == "on"
        event = set_kill_switch(
            args.state_dir,
            enabled=enabled,
            reason=args.reason,
            timestamp=args.timestamp,
        )
        print(json.dumps(event, indent=2, sort_keys=True))
    status = build_risk_status(args.state_dir, timestamp=args.timestamp)
    if args.output_json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(f"Timestamp: {status['timestamp']}")
        print(f"Blocked New Orders: {status['blocked_new_orders']}")
        print(f"Kill Switch: {status['kill_switch_enabled']}")
        print(f"Consecutive Losses: {status['consecutive_loss_count']} / {status['consecutive_loss_limit']}")
        print(f"Cooldown Remaining: {status['cooldown_remaining_cycles']}")
        print(
            "Daily Return: "
            + f"{Decimal(status['daily_return_pct']):.2%} / breaker {Decimal(status['daily_loss_circuit_breaker_pct']):.2%}"
        )
        if status["blocked_reasons"]:
            for reason in status["blocked_reasons"]:
                print(f"- {reason}")
    return 0


def cmd_risk_check(args: argparse.Namespace) -> int:
    status = build_risk_status(args.state_dir, timestamp=args.timestamp)
    if args.output_json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(f"blocked_new_orders={status['blocked_new_orders']}")
        if status["blocked_reasons"]:
            for reason in status["blocked_reasons"]:
                print(f"- {reason}")
    return 1 if status["blocked_new_orders"] else 0


def cmd_validate_strategy(args: argparse.Namespace) -> int:
    validator = StrategyValidator(args.state_dir)
    result = validator.validate(
        timestamp=args.timestamp,
        source=args.source,
        lookback_points=args.lookback_points,
        step_points=args.step_points,
        initial_capital=to_decimal(args.initial_capital) if args.initial_capital is not None else None,
    )
    entry = result.entry
    print(
        f"{entry['timestamp']} return={Decimal(entry['return_pct']):.2%} "
        + f"max_dd={Decimal(entry['max_drawdown_pct']):.2%} "
        + f"win_rate={Decimal(entry['win_rate']):.2%} profit_factor={entry['profit_factor']}"
    )
    print(
        f"closed_trades={entry['closed_trade_count']} longest_losing_streak={entry['longest_losing_streak']} "
        + f"period={entry['period_start']} -> {entry['period_end']}"
    )
    maybe_auto_report(
        args,
        task="validate-strategy",
        status=str(entry["status"]),
        did_what=(
            f"Ran walk-forward validation across {entry['execution_runs']} execution step(s) "
            + f"from {entry['period_start']} to {entry['period_end']}."
        ),
        risk_impact=(
            f"Return {Decimal(entry['return_pct']):.2%}, max drawdown {Decimal(entry['max_drawdown_pct']):.2%}, "
            + f"win rate {Decimal(entry['win_rate']):.2%}, profit factor {entry['profit_factor']}."
        ),
        next_step="Compare the latest validation summary in the dashboard with live execution behavior before changing sizing.",
        source="cli.validate-strategy",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    def add_state_dir_argument(target: argparse.ArgumentParser, *, suppress_default: bool = False) -> None:
        kwargs: dict[str, object] = {"default": "demo/state"}
        if suppress_default:
            kwargs["default"] = argparse.SUPPRESS
        target.add_argument("--state-dir", **kwargs)

    def add_report_log_argument(target: argparse.ArgumentParser, *, suppress_default: bool = False) -> None:
        kwargs: dict[str, object] = {}
        if suppress_default:
            kwargs["default"] = argparse.SUPPRESS
        target.add_argument("--report-log", **kwargs)

    def add_hook_command_argument(target: argparse.ArgumentParser) -> None:
        target.add_argument("--hook-command")

    def add_dashboard_auth_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--dashboard-bearer-env", default=DEFAULT_DASHBOARD_BEARER_ENV)
        target.add_argument("--dashboard-basic-user-env", default=DEFAULT_DASHBOARD_BASIC_USER_ENV)
        target.add_argument("--dashboard-basic-pass-env", default=DEFAULT_DASHBOARD_BASIC_PASS_ENV)

    parser = argparse.ArgumentParser(prog="sim-trading")
    add_state_dir_argument(parser)
    add_report_log_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="initialize state from a seed file")
    add_state_dir_argument(init_parser, suppress_default=True)
    add_report_log_argument(init_parser, suppress_default=True)
    add_hook_command_argument(init_parser)
    init_parser.add_argument("--seed-file", default="seeds/initial_state.json")
    init_parser.set_defaults(func=cmd_init)

    trade_parser = subparsers.add_parser("record-trade", help="record a simulated fill")
    add_state_dir_argument(trade_parser, suppress_default=True)
    add_report_log_argument(trade_parser, suppress_default=True)
    add_hook_command_argument(trade_parser)
    trade_parser.add_argument("--symbol", required=True)
    trade_parser.add_argument("--side", choices=["buy", "sell"], required=True)
    trade_parser.add_argument("--quantity", required=True)
    trade_parser.add_argument("--price", required=True)
    trade_parser.add_argument("--fee", default="0")
    trade_parser.add_argument("--timestamp")
    trade_parser.add_argument("--strategy", default="manual")
    trade_parser.add_argument("--note", default="")
    trade_parser.add_argument("--stop-loss")
    trade_parser.set_defaults(func=cmd_record_trade)

    normalize_parser = subparsers.add_parser(
        "normalize-positions",
        help="convert legacy synthetic seed-unit positions into carrying-notional market-based quantities",
    )
    add_state_dir_argument(normalize_parser, suppress_default=True)
    add_report_log_argument(normalize_parser, suppress_default=True)
    add_hook_command_argument(normalize_parser)
    normalize_parser.add_argument("--price", action="append")
    normalize_parser.add_argument("--timestamp")
    normalize_parser.add_argument(
        "--source-note",
        default=(
            "Normalized synthetic seed-unit positions into carrying-notional market-based quantities. "
            "Open positions keep their remaining notional and reset unrealized PnL from the normalization mark."
        ),
    )
    normalize_parser.set_defaults(func=cmd_normalize_positions)

    snapshot_parser = subparsers.add_parser("snapshot", help="persist a marked-to-market snapshot")
    add_state_dir_argument(snapshot_parser, suppress_default=True)
    add_report_log_argument(snapshot_parser, suppress_default=True)
    add_hook_command_argument(snapshot_parser)
    snapshot_parser.add_argument("--price", action="append")
    snapshot_parser.add_argument("--timestamp")
    snapshot_parser.set_defaults(func=lambda args: cmd_snapshot(args, persist=True))

    status_parser = subparsers.add_parser("status", help="show current marked-to-market status without persisting")
    add_state_dir_argument(status_parser, suppress_default=True)
    status_parser.add_argument("--price", action="append")
    status_parser.add_argument("--timestamp")
    status_parser.set_defaults(func=lambda args: cmd_snapshot(args, persist=False))

    report_parser = subparsers.add_parser("report", help="generate a markdown daily report")
    add_state_dir_argument(report_parser, suppress_default=True)
    add_report_log_argument(report_parser, suppress_default=True)
    add_hook_command_argument(report_parser)
    report_parser.add_argument("--date")
    report_parser.add_argument("--output")
    report_parser.set_defaults(func=cmd_report)

    notify_parser = subparsers.add_parser("notify-task", help="append a standardized task notification to the report log")
    add_state_dir_argument(notify_parser, suppress_default=True)
    add_report_log_argument(notify_parser, suppress_default=True)
    add_hook_command_argument(notify_parser)
    notify_parser.add_argument("--task", required=True)
    notify_parser.add_argument("--status", required=True)
    notify_parser.add_argument("--did-what", required=True)
    notify_parser.add_argument("--risk", required=True)
    notify_parser.add_argument("--next", required=True)
    notify_parser.add_argument("--source", default="cli.notify-task")
    notify_parser.set_defaults(func=cmd_notify_task)

    emit_parser = subparsers.add_parser("emit-status-report", help="generate and log a standardized status report from current ledger state")
    add_state_dir_argument(emit_parser, suppress_default=True)
    add_report_log_argument(emit_parser, suppress_default=True)
    add_hook_command_argument(emit_parser)
    emit_parser.add_argument("--source", default="cli.emit-status-report")
    emit_parser.add_argument("--task", default="ledger-status")
    emit_parser.add_argument("--timestamp")
    emit_parser.set_defaults(func=cmd_emit_status_report)

    webhook_parser = subparsers.add_parser("serve-webhook", help="serve POST /task-done for external task completion notifications")
    add_state_dir_argument(webhook_parser, suppress_default=True)
    add_report_log_argument(webhook_parser, suppress_default=True)
    add_hook_command_argument(webhook_parser)
    webhook_parser.add_argument("--host", default="127.0.0.1")
    webhook_parser.add_argument("--port", type=int, default=8765)
    webhook_parser.add_argument("--token-env", default="SIM_TRADING_WEBHOOK_TOKEN")
    webhook_parser.add_argument("--replay-ttl-seconds", type=int)
    webhook_parser.set_defaults(func=cmd_serve_webhook)

    dashboard_parser = subparsers.add_parser("serve-dashboard", help="serve a lightweight live status dashboard")
    add_state_dir_argument(dashboard_parser, suppress_default=True)
    add_report_log_argument(dashboard_parser, suppress_default=True)
    add_hook_command_argument(dashboard_parser)
    add_dashboard_auth_arguments(dashboard_parser)
    dashboard_parser.add_argument("--host", default="127.0.0.1")
    dashboard_parser.add_argument("--port", type=int, default=8780)
    dashboard_parser.add_argument("--limit", type=int, default=20)
    dashboard_parser.add_argument("--health-max-report-age-seconds", type=int, default=7200)
    dashboard_parser.set_defaults(func=cmd_serve_dashboard)

    rotate_parser = subparsers.add_parser("rotate-tokens", help="generate and persist new ops secrets")
    add_dashboard_auth_arguments(rotate_parser)
    rotate_parser.add_argument("--ops-env", default=".ops.env")
    rotate_parser.add_argument("--webhook-token-env", default="SIM_TRADING_WEBHOOK_TOKEN")
    rotate_parser.add_argument("--dashboard-basic-user", default="ops")
    rotate_parser.add_argument("--replay-ttl-seconds", type=int, default=300)
    rotate_parser.add_argument("--show", action="store_true")
    rotate_parser.set_defaults(func=cmd_rotate_tokens)

    health_parser = subparsers.add_parser("health-check", help="validate state files, services, and report freshness")
    add_state_dir_argument(health_parser, suppress_default=True)
    add_report_log_argument(health_parser, suppress_default=True)
    health_parser.add_argument("--dashboard-pid-file", default=".ops/run/dashboard.pid")
    health_parser.add_argument("--webhook-pid-file", default=".ops/run/webhook.pid")
    health_parser.add_argument("--dashboard-health-url", default="http://127.0.0.1:8780/api/health")
    health_parser.add_argument("--webhook-host", default="127.0.0.1")
    health_parser.add_argument("--webhook-port", type=int, default=8765)
    health_parser.add_argument("--max-report-age-seconds", type=int, default=7200)
    health_parser.add_argument("--timeout-seconds", type=int, default=3)
    health_parser.add_argument("--output-json", action="store_true")
    health_parser.set_defaults(func=cmd_health_check)

    fetch_parser = subparsers.add_parser("fetch-market", help="fetch latest public market prices and persist them")
    add_state_dir_argument(fetch_parser, suppress_default=True)
    fetch_parser.add_argument("--symbol", action="append")
    fetch_parser.add_argument("--source", default="binance")
    fetch_parser.add_argument("--api-root", default="https://api.binance.com")
    fetch_parser.add_argument("--timeout-seconds", type=int, default=10)
    fetch_parser.add_argument("--prices-only", action="store_true", help="update market_prices.json only (skip market_feed append)")
    fetch_parser.add_argument("--timestamp")
    fetch_parser.set_defaults(func=cmd_fetch_market)

    universe_parser = subparsers.add_parser(
        "universe-refresh",
        help="build the filtered Binance spot USDT universe and persist Top 120 / Top 30 artifacts",
    )
    add_state_dir_argument(universe_parser, suppress_default=True)
    add_report_log_argument(universe_parser, suppress_default=True)
    add_hook_command_argument(universe_parser)
    universe_parser.add_argument("--source", default="binance")
    universe_parser.add_argument("--api-root", default="https://api.binance.com")
    universe_parser.add_argument("--timeout-seconds", type=int, default=20)
    universe_parser.add_argument("--top-limit", type=int, default=120)
    universe_parser.add_argument("--ds-limit", type=int, default=30)
    universe_parser.add_argument("--min-listing-age-days", type=int, default=30)
    universe_parser.add_argument("--min-quote-volume", default="5000000")
    universe_parser.add_argument("--min-trade-count", type=int, default=2000)
    universe_parser.add_argument("--max-spread-pct", default="0.01")
    universe_parser.add_argument("--timestamp")
    universe_parser.set_defaults(func=cmd_universe_refresh)

    signals_parser = subparsers.add_parser("run-signals", help="compute and persist a signal snapshot from market feed history")
    add_state_dir_argument(signals_parser, suppress_default=True)
    add_report_log_argument(signals_parser, suppress_default=True)
    add_hook_command_argument(signals_parser)
    signals_parser.add_argument("--source", default="cli.run-signals")
    signals_parser.add_argument("--lookback-points", type=int, default=6)
    signals_parser.add_argument("--timestamp")
    signals_parser.add_argument("--notify", action="store_true")
    signals_parser.add_argument("--task", default="signal-run")
    signals_parser.add_argument("--notify-source", default="cli.run-signals")
    signals_parser.set_defaults(func=cmd_run_signals)

    strategy_run_parser = subparsers.add_parser(
        "strategy-run",
        help="run one isolated strategy track against the shared market feed",
    )
    add_state_dir_argument(strategy_run_parser, suppress_default=True)
    add_report_log_argument(strategy_run_parser, suppress_default=True)
    add_hook_command_argument(strategy_run_parser)
    strategy_run_parser.add_argument(
        "--strategy",
        required=True,
        choices=["baseline", "ds_conservative", "ds_aggressive"],
    )
    strategy_run_parser.add_argument("--source", default="cli.strategy-run")
    strategy_run_parser.add_argument("--lookback-points", type=int, default=6)
    strategy_run_parser.add_argument("--timestamp")
    strategy_run_parser.set_defaults(func=cmd_strategy_run)

    strategy_compare_parser = subparsers.add_parser(
        "strategy-compare",
        help="show aggregate comparison metrics across the isolated strategy tracks",
    )
    add_state_dir_argument(strategy_compare_parser, suppress_default=True)
    strategy_compare_parser.add_argument("--timestamp")
    strategy_compare_parser.add_argument("--output-json", action="store_true")
    strategy_compare_parser.set_defaults(func=cmd_strategy_compare)

    ds_shadow_parser = subparsers.add_parser(
        "ds-shadow-run",
        help="request a DeepSeek shadow decision and persist only validated simulation plans",
    )
    add_state_dir_argument(ds_shadow_parser, suppress_default=True)
    add_report_log_argument(ds_shadow_parser, suppress_default=True)
    add_hook_command_argument(ds_shadow_parser)
    ds_shadow_parser.add_argument("--source", default="cli.ds-shadow-run")
    ds_shadow_parser.add_argument("--timestamp")
    ds_shadow_parser.add_argument("--notify", action="store_true")
    ds_shadow_parser.add_argument("--task", default="ds-shadow-run")
    ds_shadow_parser.add_argument("--notify-source", default="cli.ds-shadow-run")
    ds_shadow_parser.set_defaults(func=cmd_ds_shadow_run)

    ds_approve_parser = subparsers.add_parser(
        "ds-approve-latest",
        help="approve the latest validated DeepSeek decision for one simulated execution cycle",
    )
    add_state_dir_argument(ds_approve_parser, suppress_default=True)
    add_report_log_argument(ds_approve_parser, suppress_default=True)
    add_hook_command_argument(ds_approve_parser)
    ds_approve_parser.add_argument("--source", default="cli.ds-approve-latest")
    ds_approve_parser.add_argument("--timestamp")
    ds_approve_parser.add_argument("--notify", action="store_true")
    ds_approve_parser.add_argument("--task", default="ds-approve-latest")
    ds_approve_parser.add_argument("--notify-source", default="cli.ds-approve-latest")
    ds_approve_parser.set_defaults(func=cmd_ds_approve_latest)

    execute_parser = subparsers.add_parser("execute-sim", help="run one simulation execution cycle from the latest strategy targets")
    add_state_dir_argument(execute_parser, suppress_default=True)
    add_report_log_argument(execute_parser, suppress_default=True)
    add_hook_command_argument(execute_parser)
    execute_parser.add_argument("--source", default="cli.execute-sim")
    execute_parser.add_argument("--decision-source", choices=["signals", "ds-approved", "strategy-selected"], default="signals")
    execute_parser.add_argument("--lookback-points", type=int, default=6)
    execute_parser.add_argument("--price", action="append")
    execute_parser.add_argument("--timestamp")
    execute_parser.add_argument("--notify", action="store_true")
    execute_parser.set_defaults(func=cmd_execute_sim)

    strategy_selection_parser = subparsers.add_parser(
        "strategy-selection",
        help="view or update main-account strategy selection used by execute-sim --decision-source strategy-selected",
    )
    strategy_selection_parser.add_argument("action", choices=["status", "set", "clear"])
    strategy_selection_parser.add_argument("--strategy", choices=["baseline", "ds_conservative", "ds_aggressive"])
    strategy_selection_parser.set_defaults(func=cmd_strategy_selection)

    risk_status_parser = subparsers.add_parser("risk-status", help="show current hard-risk gate state and optionally toggle kill switch")
    add_state_dir_argument(risk_status_parser, suppress_default=True)
    risk_status_parser.add_argument("--timestamp")
    risk_status_parser.add_argument("--output-json", action="store_true")
    risk_status_parser.add_argument("--kill-switch", choices=["on", "off"])
    risk_status_parser.add_argument("--reason", default="")
    risk_status_parser.set_defaults(func=cmd_risk_status)

    risk_check_parser = subparsers.add_parser("risk-check", help="exit non-zero when hard-risk gates are currently blocking new orders")
    add_state_dir_argument(risk_check_parser, suppress_default=True)
    risk_check_parser.add_argument("--timestamp")
    risk_check_parser.add_argument("--output-json", action="store_true")
    risk_check_parser.set_defaults(func=cmd_risk_check)

    validate_parser = subparsers.add_parser("validate-strategy", help="run walk-forward validation over historical market-feed snapshots")
    add_state_dir_argument(validate_parser, suppress_default=True)
    add_report_log_argument(validate_parser, suppress_default=True)
    add_hook_command_argument(validate_parser)
    validate_parser.add_argument("--source", default="cli.validate-strategy")
    validate_parser.add_argument("--timestamp")
    validate_parser.add_argument("--lookback-points", type=int)
    validate_parser.add_argument("--step-points", type=int)
    validate_parser.add_argument("--initial-capital")
    validate_parser.set_defaults(func=cmd_validate_strategy)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:  # pragma: no cover - CLI boundary
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main_init() -> int:
    return main(["init", *sys.argv[1:]])


def main_record_trade() -> int:
    return main(["record-trade", *sys.argv[1:]])


def main_snapshot() -> int:
    return main(["snapshot", *sys.argv[1:]])


def main_normalize_positions() -> int:
    return main(["normalize-positions", *sys.argv[1:]])


def main_status() -> int:
    return main(["status", *sys.argv[1:]])


def main_report() -> int:
    return main(["report", *sys.argv[1:]])


def main_notify_task() -> int:
    return main(["notify-task", *sys.argv[1:]])


def main_emit_status_report() -> int:
    return main(["emit-status-report", *sys.argv[1:]])


def main_serve_webhook() -> int:
    return main(["serve-webhook", *sys.argv[1:]])


def main_serve_dashboard() -> int:
    return main(["serve-dashboard", *sys.argv[1:]])


def main_rotate_tokens() -> int:
    return main(["rotate-tokens", *sys.argv[1:]])


def main_health_check() -> int:
    return main(["health-check", *sys.argv[1:]])


def main_fetch_market() -> int:
    return main(["fetch-market", *sys.argv[1:]])


def main_universe_refresh() -> int:
    return main(["universe-refresh", *sys.argv[1:]])


def main_run_signals() -> int:
    return main(["run-signals", *sys.argv[1:]])


def main_strategy_run() -> int:
    return main(["strategy-run", *sys.argv[1:]])


def main_strategy_compare() -> int:
    return main(["strategy-compare", *sys.argv[1:]])


def main_ds_shadow_run() -> int:
    return main(["ds-shadow-run", *sys.argv[1:]])


def main_ds_approve_latest() -> int:
    return main(["ds-approve-latest", *sys.argv[1:]])


def main_execute_sim() -> int:
    return main(["execute-sim", *sys.argv[1:]])


def main_risk_status() -> int:
    return main(["risk-status", *sys.argv[1:]])


def main_risk_check() -> int:
    return main(["risk-check", *sys.argv[1:]])


def main_validate_strategy() -> int:
    return main(["validate-strategy", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
