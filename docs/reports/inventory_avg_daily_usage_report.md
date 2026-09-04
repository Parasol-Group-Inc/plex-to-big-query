# Vox Scorecard | Avg Daily Usage

> **Status:** 🔬 Deployed 2026-09-01, 0 rows — formula still unverified against real data (see below) · **Category:** Supply Chain · **Runs:** rides the Inventory Activity pipeline

## What this tells you

For each part and month, roughly how much of it gets used (depleted) per day on average.

## Where it fits

Candidate for `Vox_Looker_DB - Inventory`'s "Avg. Daily" field — previously flagged in this repo as having no confirmed Plex source (that note was about a narrower reorder-point/MSL search; this simpler daily-average ask turns out to already be answerable). See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Takes the already-deployed `inventory_activity_report`'s monthly depletion quantity per part and divides by the number of days in that month.

- **Pipeline:** `reports/inventory_activity.yaml` → `inventory_avg_daily_usage_report`
- **SQL:** `reports/sql/inventory_avg_daily_usage_view.sql`

## Flags and open questions

- **Unverified against real data.** The underlying tables (`Part_v_Cell_Production`/`Part_v_Cell_Depletion`) were confirmed empty — schema-confirmed only, no sample values — when `inventory_activity_report` was originally built. The math is correct, but nobody has checked it against a single real depletion number yet.
## More detail

[`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md) and [`docs/reports/inventory_activity_report.md`](inventory_activity_report.md).
