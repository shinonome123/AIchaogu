# Security Notes

## Threat model

This repo is still simulation-only, but Phase2 adds more control and state surfaces:

- the dashboard exposes execution, risk, and validation state
- the universe builder now stores broader Binance market metadata and shortlist artifacts
- the strategy framework now keeps three isolated ledgers under `state/strategies/`
- the webhook accepts externally supplied status data
- `.ops.env` contains secrets that gate those interfaces
- append-only order, risk, and validation logs can reveal portfolio behavior and operator actions
- local JSON/CSV/JSONL state can still be corrupted if the host is compromised

## Controls in this repo

- No real exchange API trading path exists in this phase.
- Dashboard auth remains optional for backward compatibility, but supports bearer token or basic auth from env-backed config.
- The dashboard exposes `/api/health` for monitoring without opening the full panel.
- Webhook requests require the shared token and can enforce replay protection with `SIM_TRADING_WEBHOOK_REPLAY_TTL_SECONDS`.
- Hard execution-time controls now exist for simulated orders:
  - max position weight per symbol
  - max gross exposure
  - max concurrent positions
  - daily loss circuit breaker
  - consecutive-loss cooldown
  - global kill switch
- Risk blocks produce append-only records in `risk_events.jsonl` and rejected order events in `order_events.jsonl`.
- `rotate-tokens` updates `.ops.env` with fresh secrets and redacts them by default in CLI output.
- `universe-refresh` is still read-only against public Binance endpoints and never stores credentials.
- Triple-strategy ledgers are isolated by directory so baseline and DS runs do not share account, position, trade, or equity files.

## DeepSeek operator mode

- `SIM_TRADING_DEEPSEEK_API_KEY` is read from the environment only and is never written into state logs.
- DeepSeek output is advisory until it passes the local schema validator and the operator explicitly approves it.
- Model hallucination remains possible even with a strict JSON schema. A well-formed payload can still contain bad reasoning, poor sizing, or stale assumptions.
- `execute-sim --decision-source ds-approved` still routes through the same simulated execution engine, cash checks, max-position cap, stop-loss validation, kill switch, cooldown, and circuit breaker logic as the normal strategy path.
- The DS strategy tracks also route through the same hard gates, plus the new gross-exposure and concurrent-position caps.
- Risk gates are the final authority. DS approval does not bypass any hard execution-time block, and rejected or clipped plans remain visible in append-only audit logs.
- DS strategy profiles only change prompt bias and daily-loss thresholds. They do not enable any real execution path.

## Recommended deployment posture

- Bind dashboard and webhook to `127.0.0.1` unless a deliberate proxy layer is in front.
- Keep `.ops.env` out of version control and readable only by the operator account.
- Prefer dashboard basic auth for browser use or bearer auth for scripted API use.
- Keep webhook replay TTL at a small positive value such as `300`.
- Review `risk-status` before enabling cron execution and after any kill-switch or circuit-breaker event.
- Review `universe_top120.json` / `universe_top30.json` and the ranking rule before enabling the 15-minute strategy tick.
- Run `health-check` from cron or another supervisor and alert on non-zero exit.
- Rotate secrets after sharing access, changing hosts, or exposing the services through a new proxy/tunnel.

## Remaining limitations

- The dashboard cookie set after bearer auth is the same bearer secret, scoped to the local origin, not a separate session token.
- Append-only local logs still live in plain text; host compromise still compromises operational integrity.
- The kill switch and cooldown state are local JSON, so deleting `risk_state.json` or `risk_events.jsonl` can remove operational history.
- Public market data still comes from an unauthenticated third-party endpoint with no secondary source or signature verification.
- Listing-age filtering relies on Binance symbol metadata when available and falls back to public kline history; both are still third-party data dependencies.
- Walk-forward validation reuses snapshot prices, not full historical order book data, so slippage/liquidity assumptions remain approximate.
- DS structured outputs can still encode bad trade ideas even after schema validation, because validation only proves shape and bounds, not correctness.
- The new strategy comparison panel is informational only; it does not auto-promote or demote any strategy.
