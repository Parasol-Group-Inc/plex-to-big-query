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
-- ⚠ PRIMARY COST MODEL ONLY (2026-10-29, audit B1). The summary has a row per
-- cost model, and Plex prod has five; summing them all gave $68.41M on 10-29,
-- the same stock valued up to four times. The total now reads the model Plex
-- marks Primary_Model (4402 "Go-Live Inventory Cost 2026": material only, no
-- labor/overhead). If no model is flagged primary, the total is empty rather
-- than a multiple. Jennilyn confirmed 2026-10-30 that Plex's Inventory
-- Valuation screen uses the same Go-Live costing and is the correct figure.
--
-- ⚠ STOCK COUNTED (2026-10-30). The summary values every active container
-- except Receiving, as Plex's Inventory Valuation screen does ($15,180,711.53
-- on the 10-29 load, Plex's figure to the cent). It used to use the
-- available-stock rule of part_on_hand_inventory_report and read $11.90M.
-- uncosted_on_hand_part_count counts the same containers (see uncosted).
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per snapshot_date (the last snapshot taken that day).

WITH

summary AS (
  SELECT *
  FROM `{gcp_project}.{dataset}.inventory_valuation_summary_report`
  WHERE snapshot_date IS NOT NULL
    AND is_primary_cost_model
  -- Plex can take more than one snapshot a day; adding two would double it.
  QUALIFY snapshot_key = MAX(snapshot_key) OVER (PARTITION BY snapshot_date)
),

-- Parts in stock today with no positive cost in the primary model. Their value
-- is missing from the total, not zero — surfaced so the gap is visible. (Until
-- 2026-10-29 this only counted parts with no cost row at all, so a part costed
-- at 0 never showed and the count read 0; audit B8.) The container filter must
-- match the summary's on_hand CTE, or this counts different stock than the
-- total values; until 2026-10-30 it read part_on_hand_inventory_report.
uncosted AS (
  SELECT COUNT(*) AS uncosted_on_hand_part_count
  FROM (
    SELECT SAFE_CAST(c.Part_Key AS INT64) AS part_key,
           SUM(SAFE_CAST(c.Quantity AS FLOAT64)) AS on_hand_qty
    FROM `{gcp_project}.{dataset}.raw_Part_v_Container` c
    WHERE SAFE_CAST(c.Active AS INT64) = 1
      AND UPPER(TRIM(CAST(c.Container_Status AS STRING))) != 'RECEIVING'
    GROUP BY part_key
  ) oh
  LEFT JOIN (
    SELECT DISTINCT SAFE_CAST(s.part_key AS INT64) AS part_key
    FROM summary s
    WHERE s.is_current_snapshot AND s.part_key IS NOT NULL
      AND s.unit_cost > 0
  ) costed
    ON costed.part_key = oh.part_key
  WHERE oh.on_hand_qty > 0
    AND costed.part_key IS NULL
)

SELECT
  s.snapshot_date,
  ANY_VALUE(s.cost_model_name)                            AS cost_model_name,
  SUM(s.inventory_value)                                  AS total_inventory_value,
  COUNT(DISTINCT s.part_number)                           AS part_count,

  -- Added 2026-09-24
  LOGICAL_OR(s.is_current_snapshot)                       AS is_current_snapshot,
  -- Parts in stock with a positive cost (2026-10-30: it also counted parts
  -- costed at $0, which uncosted_on_hand_part_count counts too). The two now
  -- add up to every part in stock.
  IF(LOGICAL_OR(s.is_current_snapshot),
     COUNT(DISTINCT IF(s.on_hand_qty > 0 AND s.unit_cost > 0, s.part_key, NULL)), NULL)
                                                          AS valued_part_count,
  IF(LOGICAL_OR(s.is_current_snapshot),
     ANY_VALUE(u.uncosted_on_hand_part_count), NULL)      AS uncosted_on_hand_part_count

FROM summary s
CROSS JOIN uncosted u
GROUP BY s.snapshot_date
ORDER BY s.snapshot_date DESC
