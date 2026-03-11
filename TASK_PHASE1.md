You are Codex. Upgrade this sim-trading project to Phase-1 operations reliability.

Goals requested by user:
1) Auto-reporting so task completion/status is proactively reported.
2) Trigger interface so external tools (including Codex jobs) can notify this system when a task is done.
3) A lightweight dashboard panel for live status that can be exposed via FRP later.

Implement in this repo only. Python 3.11+, minimal dependencies.

Required work:
A. Reporting/notification module
- Add a notifier module that can:
  - build standardized report payload (did_what/current_status/risk_impact/next_step)
  - append report entries to a local report log file (JSONL)
  - optionally execute a shell hook command if configured
- Add a CLI command:
  - `notify-task` with flags:
    --task, --status, --did-what, --risk, --next, --source
  - It should write to log and print human-readable summary.

B. Trigger webhook interface
- Add a tiny HTTP server (stdlib `http.server` is fine) with endpoint:
  - POST /task-done
  - Accept JSON fields: task, status, did_what, risk_impact, next_step, source, token
- Token auth via env var `SIM_TRADING_WEBHOOK_TOKEN` (reject if mismatch).
- On success, call notifier flow and return JSON result.
- Add CLI command:
  - `serve-webhook --host --port --token-env`

C. Dashboard panel
- Add a lightweight status dashboard server:
  - endpoint `/api/status` returns current snapshot + last N notifications
  - endpoint `/` returns simple HTML panel with auto-refresh (no frameworks)
- Add CLI command:
  - `serve-dashboard --host --port --state-dir --report-log`
- Show at least: NAV, realized/unrealized PnL, drawdown, positions, latest notifications.

D. Scheduled reporting support
- Add command:
  - `emit-status-report` -> generates standardized report from current ledger status.
- Provide a sample cron setup doc/script that runs this every hour and daily summary.

E. Codex completion trigger pattern
- Add docs + script showing how external jobs (codex or any process) can POST to `/task-done`.
- Include curl examples.

F. Documentation and verification
- Update README with new commands and quick start.
- Add `OPS_GUIDE.md` covering:
  - proactive reporting model
  - webhook security token
  - dashboard serving
  - cron recommendations
  - failure modes
- Generate sample outputs under demo/:
  - demo/reports-log.jsonl entries
  - ensure dashboard/API can read them.

Quality constraints:
- Keep existing sim-trading behavior intact.
- Do not remove existing commands.
- Keep code organized and typed where possible.

At end:
- Print concise summary of changed files.
- Print exact verification commands you ran.
- Then run this command (best-effort) to notify orchestrator:
  openclaw system event --text "Done: sim-trading phase1 reporting+webhook+dashboard" --mode now
