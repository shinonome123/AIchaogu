You are Codex. Implement the formally approved Universe Expansion + Triple Strategy framework for this sim-trading project.

Already exists:
- Phase2 execution/risk/validation
- DS Stage A/B (shadow + approval)
- Dashboard/API + Chinese default UI

Now implement these requirements exactly:

A) Universe expansion pipeline
1. Source market: Binance spot USDT pairs.
2. Universe builder command (name: `universe-refresh`):
   - start from all spot *USDT symbols
   - exclude leveraged tokens: names containing UP/DOWN/BULL/BEAR
   - exclude obvious stable-stable pairs
   - exclude listing age < 60 days
   - enforce liquidity filters:
     - 24h quoteVolume >= 20,000,000 USDT
     - tradeCount >= 10,000
   - enforce spread <= 0.30%
   - produce Top 120 ranked shortlist (document ranking rule)
   - produce Top 30 DS candidate subset
3. Persist artifacts under state:
   - universe_all.json
   - universe_filtered.json
   - universe_top120.json
   - universe_top30.json
   - universe_runs.jsonl (audit)

B) Scheduling + cadence
- Keep existing 3-hour report cadence.
- Add/extend cron helper logic so the following can run:
  - every 15 min: universe-refresh
  - every 30 min: strategy runs (baseline + ds_conservative + ds_aggressive)
  - DS decision cadence every 30 min for DS strategies
- Expose toggles via env vars.

C) Triple strategy framework (independent ledgers)
Implement three strategy tracks with isolated state directories:
1) baseline (rule-based)
2) ds_conservative (DS with cautious bias)
3) ds_aggressive (DS with normal bias)

Rules:
- shared market feed, same fees/slippage assumptions
- each strategy starts with 100 USDT
- each strategy has independent account/positions/trades/equity logs

Add commands:
- `strategy-run --strategy baseline|ds_conservative|ds_aggressive`
- `strategy-compare` (aggregate table + JSON output)

D) Risk parameter profile (strategy-specific defaults)
- max position per symbol: 8%
- max gross exposure: 60%
- max concurrent positions: 10
- daily loss breaker:
  - ds_conservative: -2.5%
  - ds_aggressive: -4.0%
  - baseline: choose reasonable default and document
- consecutive loss cooldown: 3 losses => cooldown 3 cycles
- default stop loss: 3.5%
- keep kill switch support

E) Dashboard/API additions
- Add universe status panel:
  - counts for all / filtered / top120 / top30
  - latest universe refresh timestamp
- Add strategy comparison panel:
  - return, max drawdown, win rate, profit factor, turnover, risk-trigger count
- Keep Chinese default and en switch.

F) Docs + verification
- Update README / OPS_GUIDE / SECURITY_NOTES.
- Add verification script(s) to check:
  - universe filter outputs
  - independent strategy state isolation
  - strategy-compare output
  - dashboard API fields for universe + compare
- Provide demo outputs.

Compatibility/safety:
- Do not break existing commands.
- Keep simulation-only.
- No hardcoded secrets.
- Minimal dependencies.

At end output:
- changed files
- verification commands
- remaining known gaps

When completely finished, run:
openclaw system event --text "Done: universe expansion + triple strategy framework" --mode now
