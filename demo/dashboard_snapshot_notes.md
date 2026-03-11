# Dashboard Snapshot Notes

Reference date: 2026-03-11

Sample navigation:

- `/` opens the `Overview` workspace tab.
- `/?view=baseline` opens the baseline strategy panel.
- `/?view=ds_conservative` opens the cautious DS panel.
- `/?view=ds_aggressive` opens the aggressive DS panel.
- Append `&lang=en` to any of the above for English labels.

Expected center-stage sections:

- `Overview`: root NAV chart, strategy comparison table, root open positions table.
- `baseline`: strategy KPI strip, strategy NAV chart, positions summary, positions table, recent trades, recent events.
- `ds_conservative`: same as baseline plus DS-aware ops panel content in the right rail.
- `ds_aggressive`: same as `ds_conservative`, with rejection/risk activity visible when present.

Layout notes:

- Left rail keeps market monitor and notifications.
- Center rail holds the tabbed strategy workspace and price trends.
- Right rail keeps execution, risk, validation, and DS operator detail aligned to the active tab.
