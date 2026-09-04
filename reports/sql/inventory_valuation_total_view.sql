-- inventory_valuation_total_report — single total inventory dollar value
-- per snapshot date (Plex-native candidate for the Vox Nutrition
-- Scorecard's Flow funnel "Inventory Val" phase — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- Thin alias over the already-deployed inventory_valuation_summary_report
-- (same config/pipeline) — MUST stay listed after it in
-- reports/inventory_snapshot.yaml's bq_view list.
--
-- SCOPE LIMIT: this is ONE total across all cost sub-types, not a
-- WIP-vs-Finished-Goods-vs-Raw split. Cost_Sub_Type_Key has no confirmed
-- label lookup anywhere in this repo (see inventory_snapshot_view.sql's
-- own header comment) — splitting this total into those categories is a
-- separate, currently-blocked question, not solved by this view. Fine if
-- the Flow funnel's "Inventory Val" phase just means one grand total; not
-- fine if it needs to be broken out by category.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per snapshot_date.

SELECT
  snapshot_date,
  SUM(total_cost)              AS total_inventory_value,
  COUNT(DISTINCT part_number)  AS part_count
FROM `{gcp_project}.{dataset}.inventory_valuation_summary_report`
WHERE snapshot_date IS NOT NULL
GROUP BY snapshot_date
ORDER BY snapshot_date DESC
