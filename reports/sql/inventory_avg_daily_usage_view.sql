-- inventory_avg_daily_usage_report — average daily depletion (usage) rate
-- per part per month (Plex-native candidate for the Vox Nutrition
-- Scorecard's Inventory "Avg. Daily" field — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- Thin alias over the already-deployed inventory_activity_report (same
-- config/pipeline) — MUST stay listed after it in
-- reports/inventory_activity.yaml's bq_view list.
--
-- UNVERIFIED AGAINST REAL DATA: inventory_activity_view.sql's own header
-- notes that Part_v_Cell_Production/Part_v_Cell_Depletion were both EMPTY
-- (schema-confirmed only, no sample values) when that view was built. This
-- average is mathematically correct once real depletion data lands, but
-- has not been checked against a single real value yet — re-verify once
-- this tenant has some.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (part, month).

SELECT
  part_key,
  part_number,
  part_name,
  activity_month,
  depleted_quantity,
  SAFE_DIVIDE(
    depleted_quantity,
    DATE_DIFF(DATE_ADD(activity_month, INTERVAL 1 MONTH), activity_month, DAY)
  )                                                AS avg_daily_usage
FROM `{gcp_project}.{dataset}.inventory_activity_report`
