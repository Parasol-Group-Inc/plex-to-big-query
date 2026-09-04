# Vox Scorecard | Inventory Value Total

> **Status:** ✅ Deployed and verified 2026-09-01 — 0 rows, confirmed genuinely empty (`Part_v_Snapshot` has no real rows yet on this tenant), not a query bug · **Category:** Inventory · **Runs:** rides the Inventory Snapshot pipeline

## What this tells you

One number per snapshot date: the total dollar value of all inventory Plex has costed, plus how many distinct parts that total covers.

## Where it fits

Candidate for the "Inventory Val" phase of the Vox Nutrition Scorecard's Flow revenue funnel (`Vox_Looker_DB - Flow`), currently one of the funnel's 3 unbuilt phases. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

A simple sum of the already-deployed `inventory_valuation_summary_report`'s per-part cost, grouped by snapshot date.

- **Pipeline:** `reports/inventory_snapshot.yaml` → `inventory_valuation_total_report`
- **SQL:** `reports/sql/inventory_valuation_total_view.sql`

## Flags and open questions

- **One total only — not split by WIP/Finished Goods/Raw Material.** `Cost_Sub_Type_Key` (the column that would distinguish those categories) has no confirmed label lookup anywhere in this repo. Fine if the Flow funnel's "Inventory Val" phase just needs one grand total; not fine if it needs to be broken into categories — that's a separate, currently-blocked question.
## More detail

[`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md) and [`docs/reports/inventory_valuation_summary_report.md`](inventory_valuation_summary_report.md).
