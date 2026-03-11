You are Codex. Continue this sim-trading project.

User request (approved):
1) Start implementing "position normalization" to avoid misleading NAV from synthetic seed quantities.
2) Upgrade web dashboard with charts:
   - equity/NAV curve
   - current held-coin price curves (from market feed history)
3) Add Chinese localization for web UI (default Chinese), keep English compatibility if practical.

Constraints:
- Simulation only. No real exchange trading execution.
- Keep existing commands working.
- Minimal dependencies; prefer stdlib and vanilla frontend.
- Work only in this repo.

Required deliverables:
A. Data/normalization layer
- Add a migration or normalization command to convert current synthetic-unit seed holdings to a notional-consistent representation.
- Preserve audit trail (before/after snapshot + source note).
- Ensure status/report output clearly marks normalized mode.

B. Dashboard charts
- Extend `/api/status` (or add new API) to return timeseries data for:
  - equity_curve NAV timeline
  - market feed price timeline per symbol
- Update dashboard HTML to render charts (canvas + lightweight JS; Chart.js CDN acceptable).
- Show at least:
  - NAV curve
  - per-symbol price mini-trends for held assets

C. Chinese localization
- Default UI text to Chinese.
- Provide simple i18n structure (dictionary-based), with optional lang switch (zh/en).
- Translate key labels: NAV, drawdown, positions, notifications, signals, health, etc.

D. Docs + verification
- Update README / OPS_GUIDE with new commands and chart/i18n usage.
- Add verification script for API payload structure and dashboard render-critical fields.
- Include demo sample outputs if needed.

At end, output:
- changed files
- verification commands
- remaining risks

When completely finished, run:
openclaw system event --text "Done: sim-trading ui charts + zh localization + normalization" --mode now
