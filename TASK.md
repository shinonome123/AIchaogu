You are Codex acting as a software engineer.

Goal:
Build a v1 "sim-trading" system (simulation only, no real exchange API) in this repo.

Important constraints:
- Do NOT touch files outside this workdir.
- Create production-like structure and clear docs.
- Python 3.11+ compatible.

Required deliverables:
1) sim-trading/ project with modules for:
   - ledger (cash/positions/trades/equity curve)
   - risk (max position size, daily loss cap, stop-loss config)
   - strategy interface + one example strategy
   - report generator (markdown daily report: NAV, drawdown, win-rate, PnL stats)
2) CLI entrypoints/scripts for:
   - init
   - record trade
   - snapshot/status
   - generate daily report
3) Migrate initial state from context/sim-trading.md into a machine-readable seed file with source note.
4) README.md with usage and architecture.
5) REFACTOR_LOG.md with:
   - modules changed/created
   - data schema
   - risk rules
   - known risks/next steps toward small real-money trial readiness.
6) Provide runnable demo/sample data and generate one sample report file.

Implementation preference:
- Keep dependencies minimal.
- Use JSON/CSV for storage (simple, inspectable).
- Ensure idempotent init behavior.

At the end, output a concise summary listing created files and run commands used for verification.
