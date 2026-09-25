# Vox Scorecard | Avg Daily Usage

> **Status:** 🔬 Deployed 2026-09-01, 0 rows — formula still unverified against real data (see below) · **Category:** Supply Chain · **Runs:** rides the Inventory Activity pipeline

## What this tells you

For each part and month, roughly how much of it gets used (depleted) per day on average.

## Where it fits

Candidate for `Vox_Looker_DB - Inventory`'s "Avg. Daily" field — previously flagged in this repo as having no confirmed Plex source (that note was about a narrower reorder-point/MSL search; this simpler daily-average ask turns out to already be answerable). See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Takes the already-deployed `inventory_activity_report`'s monthly depletion quantity per part and divides by the days in that month — or, for the month in progress, the days elapsed so far.

- **Pipeline:** `reports/inventory_activity.yaml` → `inventory_avg_daily_usage_report`
- **SQL:** `reports/sql/inventory_avg_daily_usage_view.sql`

## Flags and open questions

- **⚠ Fixed 2026-09-24 — the month in progress read low.** Every month was divided by its full calendar length, so on the 24th, 24 days of usage were spread over 30 days (~20% low). Now a finished month divides by all its days, the **current month by days elapsed through today** (today included — the same calendar rule as the run-rate tile's "% into month"), and a future month gives no average. Through today rather than through the last usage date on purpose: a day with no usage is a real zero day, and the last-activity rule would inflate idle parts. New columns: `days_in_period`, `is_month_in_progress`, `unit`. Fixed on branch `dev-sandbox`, not deployed. Found by the scorecard sandbox.
- **One row per part, in that part's own unit — never sum it across parts.** A single "Avg. Daily" tile that totals every part adds capsules to bottles to kilograms. The new `unit` column (Plex `Part_v_Part.Unit`; often blank on this tenant) is there so a Looker tile can filter to one part or one unit. This view does not convert units.
- **Unverified against real data.** The underlying tables (`Part_v_Cell_Production`/`Part_v_Cell_Depletion`) were confirmed empty — schema-confirmed only, no sample values — when `inventory_activity_report` was originally built. The math is correct, but nobody has checked it against a single real depletion number yet.
## More detail

[`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md) and [`docs/reports/inventory_activity_report.md`](inventory_activity_report.md).
