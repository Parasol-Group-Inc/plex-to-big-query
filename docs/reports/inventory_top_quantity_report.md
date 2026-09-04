# Vox Scorecard | Top Quantity Ranking

> **Status:** ✅ Deployed and verified 2026-09-01 — 0 rows, confirmed genuinely empty (`Part_v_Container` has no real rows yet on this tenant), not a query bug · **Category:** Supply Chain · **Runs:** rides the Part On-Hand Inventory pipeline

## What this tells you

Every part ranked by how much of it is currently on hand, highest first.

## Where it fits

Candidate for the "Top Quantity" half of the Vox Nutrition Scorecard's `vw_top_overstock` (a BigQuery source in the Monday.com-fed `voxdatalake.VoxScorecardsLive` dataset). See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Ranks the already-deployed `part_on_hand_inventory_report` by on-hand quantity.

- **Pipeline:** `reports/part_on_hand_inventory.yaml` → `inventory_top_quantity_report`
- **SQL:** `reports/sql/inventory_top_quantity_view.sql`

## Flags and open questions

- **Quantity ranking only — no "Top Value" ranking yet.** That half of `vw_top_overstock` needs a $ figure joined in from a different pipeline's raw tables (`inventory_snapshot`'s cost tables), which would be this repo's first cross-pipeline raw-table dependency. Deliberately deferred rather than shipped with an untested dependency pattern — see the migration map doc.
## More detail

[`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md) and [`docs/reports/part_on_hand_inventory_report.md`](part_on_hand_inventory_report.md).
