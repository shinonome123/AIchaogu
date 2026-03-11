You are Codex. Continue upgrading this sim-trading system.

Scope for this run (user-approved):
A) Safety + stability hardening
B) First half of automated trading loop (market data collector + scheduled signal task, simulation-only)

Constraints:
- Work ONLY in this repo.
- Keep Python 3.11+ compatibility.
- Minimal dependencies; stdlib preferred.
- Preserve existing CLI behavior; extend without breaking.

A) Safety + stability hardening (required)
1. Dashboard access control:
   - Add optional auth gate for dashboard endpoints (`/` and `/api/status`).
   - Support either bearer token header or basic auth from env/config.
   - If auth not configured, keep backward compatibility but log warning in startup output.
2. Webhook security hardening:
   - Keep token check, add timestamp + nonce replay protection option (configurable TTL).
   - Add clear 401/403/409 responses.
3. Token rotation support:
   - Add CLI command `rotate-tokens` to generate new secure token(s), write to `.ops.env` template safely (without printing full secrets unless --show).
4. Service resilience:
   - Add scripts for guarded start/restart/check (`ops_start.sh`, `ops_status.sh`, `ops_restart.sh`) for dashboard+webhook.
   - Include PID/log handling.
5. Health + alert path:
   - Add `/api/health` endpoint.
   - Add CLI `health-check` that validates state files, services, and recent report-log freshness.

B) Automated loop (simulation-only, first half)
1. Market data collector:
   - Add module that fetches latest prices for configured symbols from a public endpoint (no API key).
   - Cache to `state/market_feed.jsonl` (append) and update current marks.
   - Add CLI `fetch-market` with symbol list and source.
2. Scheduled signal task:
   - Add strategy runner command `run-signals` that:
     - reads latest market feed
     - computes simple signal snapshot (momentum/ema slope or similar existing approach)
     - writes `state/signal_runs.jsonl`
     - optionally emits status notification via existing notifier
3. Cron integration:
   - Extend cron helper to include hourly `fetch-market` + `run-signals` before `emit-status-report`.
4. Dashboard extension:
   - Show latest signal run summary + market fetch timestamp on panel and `/api/status`.

Docs + verification:
- Update README and OPS_GUIDE for new auth/security/automation flows.
- Add SECURITY_NOTES.md with threat model and recommended deployment posture.
- Add verification script(s) and run them.
- Generate sample demo outputs for new files.

At end, print:
- changed files
- verification commands run
- known remaining risks

When completely finished, run:
openclaw system event --text "Done: sim-trading hardening + market fetch + signal scheduler" --mode now
