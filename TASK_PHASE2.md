You are Codex. Upgrade this sim-trading project to Phase2 execution + hard risk controls + validation.

Context:
- Existing project already has dashboard/webhook/auth/market fetch/signal snapshot/normalization.
- This phase is simulation-only (NO real exchange API trading).

Goals (must implement):
1) Simulation execution engine
   - Convert strategy targets/signals into simulated orders and fills.
   - Add order lifecycle with at least: pending, partial, filled, canceled, rejected.
   - Persist to state files (new JSON/CSV as needed) with append-only history where possible.
   - Support slippage and fees in execution results.

2) Hard risk gates (execution-time blocking, not only alerts)
   - Max position weight per symbol (e.g. configurable, default 0.25).
   - Daily loss circuit breaker (configurable, default -3%).
   - Consecutive loss throttle / cooldown (configurable).
   - Global kill switch flag to block new orders.
   - When blocked, write explicit risk-rejection records and notifications.

3) Strategy validation framework (lightweight but real)
   - Add rolling/walk-forward style validation command over historical market_feed snapshots.
   - Produce metrics: return, max drawdown, win rate, profit factor, longest losing streak.
   - Save validation runs to state and expose latest summary in API/dashboard.

4) CLI and ops integration
   - Add commands (names can vary but must cover):
     - execute-sim (run one simulation execution cycle)
     - risk-check / risk-status
     - validate-strategy
   - Extend cron helper to optionally run execution cycle and periodic validation.
   - Keep 3-hour reporting behavior compatible with current user preference.

5) Dashboard/API upgrades
   - Show latest execution summary (orders/fills/rejections)
   - Show risk gate status and last circuit-breaker event
   - Show latest validation summary and key metrics
   - Keep Chinese default UI; preserve zh/en switch.

6) Documentation + verification
   - Update README, OPS_GUIDE, SECURITY_NOTES as needed.
   - Add verification script(s) for new APIs/commands/state outputs.
   - Include sample demo outputs.

Constraints:
- Python 3.11+.
- Minimal dependencies (prefer stdlib + existing stack).
- Preserve backward compatibility for existing commands.
- Do not touch files outside this repo.

At completion output:
- changed files
- verification commands run
- remaining risks/gaps before small real-money trial

When completely finished, run:
openclaw system event --text "Done: sim-trading phase2 execution+risk+validation" --mode now
