-- inventory_valuation_total_report — single total inventory dollar value
-- per snapshot date (Plex-native candidate for the Vox Nutrition
-- Scorecard's Flow funnel "Inventory Val" phase — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- Thin alias over the already-deployed inventory_valuation_summary_report
-- (same config/pipeline) — MUST stay listed after it in
-- reports/inventory_snapshot.yaml's bq_view list.
--
-- ⚠ REWRITTEN 2026-09-24 — it used to SUM(total_cost), i.e. add up per-unit
-- standard costs with no quantity (≈ $77 for the whole building). It now
-- sums the summary's inventory_value = on-hand quantity × per-unit cost.
-- See inventory_valuation_summary_view.sql for the cost rule.
--
-- ⚠ ONLY THE CURRENT SNAPSHOT HAS A VALUE. Plex's Part_v_Snapshot is a cost
-- snapshot with no quantity, and the only on-hand this repo extracts is
-- today's (Part_v_Container). Earlier snapshot dates keep their row — part
-- count and cost are real — but total_inventory_value is NULL there, not a
-- guess. A month-end trend needs historical on-hand that is not extracted.
--
-- SCOPE LIMIT: this is ONE total across all cost sub-types, not a
-- WIP-vs-Finished-Goods-vs-Raw split. Cost_Sub_Type_Key has no confirmed
-- label lookup anywhere in this repo (see inventory_snapshot_view.sql's
-- own header comment) — splitting this total into those categories is a
-- separate, currently-blocked question, not solved by this view.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per snapshot_date (the last snapshot taken that day).

WITH

summary AS (
  SELECT *
  FROM `{gcp_project}.{dataset}.inventory_valuation_summary_report`
  WHERE snapshot_date IS NOT NULL
  -- Plex can take more than one snapshot a day; adding two would double it.
  QUALIFY snapshot_key = MAX(snapshot_key) OVER (PARTITION BY snapshot_date)
),

-- Parts physically on hand today that no cost row covers. Their value is
-- missing from the total, not zero — surfaced so the gap is visible.
uncosted AS (
  SELECT COUNT(*) AS uncosted_on_hand_part_count
  FROM `{gcp_project}.{dataset}.part_on_hand_inventory_report` oh
  WHERE SAFE_CAST(oh.on_hand_qty AS FLOAT64) > 0
    AND SAFE_CAST(oh.part_key AS INT64) NOT IN (
          SELECT SAFE_CAST(s.part_key AS INT64)
          FROM summary s
          WHERE s.is_current_snapshot AND s.part_key IS NOT NULL)
)

SELECT
  s.snapshot_date,
  SUM(s.inventory_value)                                  AS total_inventory_value,
  COUNT(DISTINCT s.part_number)                           AS part_count,

  -- Added 2026-09-24
  LOGICAL_OR(s.is_current_snapshot)                       AS is_current_snapshot,
  IF(LOGICAL_OR(s.is_current_snapshot),
     COUNT(DISTINCT IF(s.on_hand_qty > 0, s.part_key, NULL)), NULL)
                                                          AS valued_part_count,
  IF(LOGICAL_OR(s.is_current_snapshot),
     ANY_VALUE(u.uncosted_on_hand_part_count), NULL)      AS uncosted_on_hand_part_count

FROM summary s
CROSS JOIN uncosted u
GROUP BY s.snapshot_date
ORDER BY s.snapshot_date DESC
