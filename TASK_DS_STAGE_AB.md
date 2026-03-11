You are Codex. Implement DeepSeek-driven operator mode (Stage A/B) for this sim-trading project.

Goals:
- Stage A (shadow mode): DeepSeek generates structured trade intentions; system logs + dashboard show them, but no auto-execution.
- Stage B (approval mode): operator can explicitly approve latest DeepSeek plan for one execution cycle.

Important constraints:
- Simulation only. NO real exchange trading API.
- Keep existing Phase2 features intact.
- Python 3.11+, minimal dependencies.
- Do NOT hardcode secrets. Read API key from env only.

Required implementation:

1) DeepSeek client + config
- Add module (e.g., sim_trading/ds_operator.py) with:
  - base_url default: https://api.deepseek.com
  - model default configurable (e.g. deepseek-chat / deepseek-reasoner or custom string)
  - timeout/retry basic handling
- Read env/config keys:
  - SIM_TRADING_DEEPSEEK_API_KEY
  - SIM_TRADING_DEEPSEEK_BASE_URL
  - SIM_TRADING_DEEPSEEK_MODEL
  - SIM_TRADING_DEEPSEEK_ENABLED (0/1)
- If key missing/disabled: graceful no-op result with explicit reason.

2) Structured decision schema (strict)
- Define JSON schema validator (stdlib-based checks okay) for DS output:
  - market_regime: trending|ranging|risk_off
  - global_risk_mode: normal|cautious|defensive
  - decisions[] items:
    symbol, action(buy|sell|hold), target_weight(0..1), confidence(0..1), entry_reason, invalidation, stop_loss_pct, take_profit_pct
  - optional no_trade_reason
- Invalid payload => reject and write rejection log.

3) Data/log storage
- Add append-only files under state:
  - ds_requests.jsonl (prompt/meta only; NO secret key)
  - ds_decisions.jsonl (validated outputs)
  - ds_rejections.jsonl (validation/API failures)
  - ds_approvals.jsonl (manual approvals)
- Include timestamps and sources for auditability.

4) CLI commands
Add commands:
- ds-shadow-run
  - builds context from latest market feed + signal snapshot + risk status + positions
  - calls DS
  - validates output
  - writes ds_decisions or ds_rejections
  - optionally notify summary
- ds-approve-latest
  - marks latest valid DS decision as approved for next execution cycle
  - writes ds_approvals
- execute-sim
  - extend with optional `--decision-source ds-approved`:
    if set, consume latest approved DS decision targets for this cycle

5) Risk integration
- DS decisions must pass existing hard risk gates at execution time.
- Add conversion rule from decision.action/target_weight -> execution targets.
- If DS suggests out-of-bound weights, clip or reject with explicit reason logged.

6) Dashboard/API
- Extend /api/status with:
  - latest_ds_decision summary
  - latest_ds_rejection summary
  - latest_ds_approval summary
  - ds_mode (disabled/shadow/approval)
- Add dashboard cards/panels (Chinese default, keep zh/en switch):
  - DS 决策状态 / DS Decision
  - 最新 DS 选币建议
  - 最新拒绝原因

7) Cron integration (non-spam)
- Add optional env toggles in cron_phase1.sh:
  - RUN_DS_SHADOW=1/0
  - DS_SHADOW_EVERY_HOURS (default 1)
- In hourly flow: run ds-shadow-run when enabled.
- Keep user preference: status reports stay 3-hour cadence.

8) Docs + verification
- Update README and OPS_GUIDE with DS setup and safety notes.
- Add SECURITY_NOTES section about model hallucination/decision risk and why risk gates are final authority.
- Add verification script(s) for DS schema validation and status payload fields.

At completion provide:
- changed files
- verification commands
- remaining gaps before autonomous simulated trading

When completely finished, run:
openclaw system event --text "Done: sim-trading DS stage A/B integrated" --mode now
