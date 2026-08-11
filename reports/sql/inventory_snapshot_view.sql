-- inventory_snapshot_report — Current Inventory Snapshot / Vox | Inventory
-- Valuation Summary Transaction (NetSuite parity)
--
-- Join chain confirmed live against vox.test.odbc.plex.com on 2026-08-10 —
-- see docs/NETSUITE_REPORT_BUILD_PLAN.md (#15/#73/#74) and the header comment
-- in reports/inventory_snapshot.yaml for the full investigation, including
-- the standard-cost-vs-physical-quantity caveat.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- GRAIN: one row per (snapshot, part, cost sub-type) — i.e. one row per cost
-- component captured for a part at a given snapshot. This is transaction/
-- detail-level; see reports/sql/inventory_valuation_summary_view.sql for the
-- SUM(Cost)-per-part rollup built from these same raw tables.

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

  -- No confirmed label lookup for Cost_Sub_Type_Key yet — exposed raw.
  SAFE_CAST(h.Cost_Sub_Type_Key AS INT64)               AS cost_sub_type_key,
  SAFE_CAST(h.Cost AS FLOAT64)                          AS cost,

  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(h.Change_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(h.Change_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(h.Change_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS cost_change_date

FROM `{gcp_project}.{dataset}.raw_Part_v_Snapshot` s

-- Pointer table: (Snapshot_Key, Change_Key), no inline values on its own.
JOIN `{gcp_project}.{dataset}.raw_Part_v_Snapshot_Cost_Sub_Type_Breakdown` ptr
  ON SAFE_CAST(s.Snapshot_Key AS INT64) = SAFE_CAST(ptr.Snapshot_Key AS INT64)

-- Resolves Change_Key to the actual Part_Key / Cost_Sub_Type_Key / Cost.
-- NOTE: source column is "Change_key" (lowercase k) on this view — confirmed live.
JOIN `{gcp_project}.{dataset}.raw_Part_v_Cost_Sub_Type_Breakdown_History` h
  ON SAFE_CAST(ptr.Change_Key AS INT64) = SAFE_CAST(h.Change_key AS INT64)

-- Part_v_Part is shared with the sales_orders pipeline — not re-extracted here.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(h.Part_Key AS INT64) = p.Part_Key
