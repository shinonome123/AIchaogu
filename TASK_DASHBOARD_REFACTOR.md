You are Codex. Refactor and improve the existing sim-trading dashboard UX/layout without changing visual style theme.

User requests (must satisfy):
1) Current dashboard right side is too long, center area feels empty.
2) Project feels fragmented/messy; improve structure and maintainability.
3) Add separate panels/views for the three strategies (baseline, ds_conservative, ds_aggressive).
4) Keep existing style direction (no full redesign/theme swap).

Implementation requirements:
A) Layout optimization (same style, better information architecture)
- Rebalance dashboard to avoid long single-column stacking.
- Use clearer sections with compact cards and consistent heights where possible.
- Ensure center area contains meaningful content (e.g., key summary + active strategy detail + charts).
- Keep responsive behavior for narrower screens.

B) Strategy-specific views
- Add strategy switcher (tabs/segmented control) for:
  - Overview (cross-strategy compare)
  - baseline
  - ds_conservative
  - ds_aggressive
- For each strategy view, show:
  - NAV / return / drawdown / risk triggers
  - latest execution summary
  - latest DS status if applicable
  - positions summary and recent trades/events
- Add API support if needed (e.g., strategy detail endpoint), but keep backward compatibility.

C) Reduce code fragmentation
- Refactor large inline HTML/JS blocks into clearer internal sections/modules where possible.
- Improve naming and organization in server/dashboard code.
- Keep dependencies minimal.

D) Maintain existing capabilities
- Do NOT remove current cards/features (risk, DS status, universe status, comparison, notifications, i18n zh/en).
- Keep existing auth and API behavior compatible.

E) Verification
- Add/update verification script to assert:
  - strategy tabs data exists
  - layout-critical fields available via API
  - existing endpoints still work
- Provide demo screenshots or sample HTML snapshot notes if feasible.

F) Docs
- Update README/OPS docs with:
  - new strategy panel usage
  - navigation behavior
  - any new endpoint(s)

At the end output:
- changed files
- verification commands
- remaining UX gaps

When completely finished, run:
openclaw system event --text "Done: dashboard layout refined + per-strategy panels" --mode now
