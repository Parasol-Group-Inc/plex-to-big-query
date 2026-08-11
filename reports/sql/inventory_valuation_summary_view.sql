-- inventory_valuation_summary_report — Vox | Inventory Valuation Summary (NetSuite parity)
--
-- Wired into reports/inventory_snapshot.yaml as the second entry in that
-- report's bq_view list (main.py's bq_view now accepts a list — added
-- specifically to support this, see main.py's bq_view_configs/
-- validate_bq_view). Reads the SAME raw tables that report extracts
-- (Part_v_Snapshot, Part_v_Snapshot_Cost_Sub_Type_Breakdown,
-- Part_v_Cost_Sub_Type_Breakdown_History, Part_v_Part) — no extraction of
-- its own, just a second CREATE OR REPLACE VIEW from one run. See
-- docs/NETSUITE_REPORT_BUILD_PLAN.md (#73) for the confirmation log.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime (or by
-- whatever runs this manually) using the GCP_PROJECT and BQ_DATASET values.
--
-- GRAIN: one row per (snapshot, part) — Cost summed across all cost
-- sub-types captured for that part at that snapshot. Same
-- standard-cost-vs-physical-quantity caveat as inventory_snapshot_view.sql
-- applies — confirm with the report requester what "valuation" should mean
-- before treating this as a final deliverable.

SELECT
  SAFE_CAST(s.Snapshot_Key AS INT64)                    AS snapshot_key,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(s.Snapshot_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(s.Snapshot_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(s.Snapshot_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS snapshot_date,
  SAFE_CAST(s.Cost_Model_Key AS INT64)                  AS cost_model_key,

  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  SUM(SAFE_CAST(h.Cost AS FLOAT64))                     AS total_cost,
  COUNT(*)                                              AS cost_sub_type_count

FROM `{gcp_project}.{dataset}.raw_Part_v_Snapshot` s

JOIN `{gcp_project}.{dataset}.raw_Part_v_Snapshot_Cost_Sub_Type_Breakdown` ptr
  ON SAFE_CAST(s.Snapshot_Key AS INT64) = SAFE_CAST(ptr.Snapshot_Key AS INT64)

-- NOTE: source column is "Change_key" (lowercase k) on this view — confirmed live.
JOIN `{gcp_project}.{dataset}.raw_Part_v_Cost_Sub_Type_Breakdown_History` h
  ON SAFE_CAST(ptr.Change_Key AS INT64) = SAFE_CAST(h.Change_key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(h.Part_Key AS INT64) = p.Part_Key

GROUP BY snapshot_key, snapshot_date, cost_model_key, p.Part_No, p.Name
