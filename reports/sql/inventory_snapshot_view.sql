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
-- GRAIN: one row per (snapshot, cost model, part, operation, cost sub-type) —
-- the cost component in force for a part at a given snapshot. Detail level;
-- inventory_valuation_summary_view.sql rolls the same rows up per part.
--
-- ⚠ FIXED 2026-10-19 (prod-views audit). This view INNER JOINed Plex's
-- snapshot pointer table, Part_v_Snapshot_Cost_Sub_Type_Breakdown, which is
-- EMPTY in real Plex (PlexTest and PlexProd), so the view returned 0 rows in
-- both. The sibling valuation summary already handled that on 2026-09-24; the
-- snap / hist / ptr / candidate / in_force steps below are copied from it
-- verbatim, so both views agree on which cost rows a snapshot sees:
--   - Plex's own pointer rows when a snapshot has any;
--   - otherwise the latest history row per (cost model, part, operation,
--     cost sub-type) changed on or before the snapshot date.
-- Columns kept as before; cost_model_key now falls back to the history row's
-- model (the snapshot's own is NULL in real Plex), and cost_source /
-- part_operation_key are added at the end.


WITH

snap AS (
  SELECT
    SAFE_CAST(s.Snapshot_Key AS INT64)                  AS snapshot_key,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(s.Snapshot_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(s.Snapshot_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(s.Snapshot_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                                   AS snapshot_date,
    -- NULL on the real snapshot; used only as a filter when Plex does set it.
    SAFE_CAST(s.Cost_Model_Key AS INT64)                AS snapshot_cost_model_key
  FROM `{gcp_project}.{dataset}.raw_Part_v_Snapshot` s
),

-- NOTE: source column is "Change_key" (lowercase k) on this view — confirmed live.
hist AS (
  SELECT
    SAFE_CAST(h.Change_key AS INT64)                    AS change_key,
    SAFE_CAST(h.Cost_Model_Key AS INT64)                AS cost_model_key,
    SAFE_CAST(h.Part_Key AS INT64)                      AS part_key,
    SAFE_CAST(h.Part_Operation_Key AS INT64)            AS part_operation_key,
    SAFE_CAST(h.Cost_Sub_Type_Key AS INT64)             AS cost_sub_type_key,
    SAFE_CAST(h.Cost AS FLOAT64)                        AS cost,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(h.Change_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(h.Change_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(h.Change_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                                   AS change_date,
    -- Timestamp only to order two changes on the same day.
    COALESCE(
      TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(h.Change_Date AS STRING) AS INT64), 0), 1000)),
      SAFE_CAST(CAST(h.Change_Date AS STRING) AS TIMESTAMP)
    )                                                   AS change_ts
  FROM `{gcp_project}.{dataset}.raw_Part_v_Cost_Sub_Type_Breakdown_History` h
),

ptr AS (
  SELECT
    SAFE_CAST(p.Snapshot_Key AS INT64)                  AS snapshot_key,
    SAFE_CAST(p.Change_Key AS INT64)                    AS change_key
  FROM `{gcp_project}.{dataset}.raw_Part_v_Snapshot_Cost_Sub_Type_Breakdown` p
),

-- (a) the cost rows each snapshot sees
candidate AS (
  -- Plex's own membership, for snapshots that have pointer rows
  SELECT s.snapshot_key, s.snapshot_date, 'snapshot pointer' AS cost_source, h.*
  FROM snap s
  JOIN ptr
    ON SAFE_CAST(ptr.snapshot_key AS INT64) = SAFE_CAST(s.snapshot_key AS INT64)
  JOIN hist h
    ON SAFE_CAST(h.change_key AS INT64) = SAFE_CAST(ptr.change_key AS INT64)
  WHERE s.snapshot_cost_model_key IS NULL OR h.cost_model_key = s.snapshot_cost_model_key

  UNION ALL

  -- as-of fallback, for snapshots with none (every real snapshot today)
  SELECT s.snapshot_key, s.snapshot_date, 'cost history as of snapshot date' AS cost_source, h.*
  FROM snap s
  JOIN hist h
    ON h.change_date <= s.snapshot_date
  WHERE s.snapshot_key NOT IN (SELECT snapshot_key FROM ptr WHERE snapshot_key IS NOT NULL)
    AND (s.snapshot_cost_model_key IS NULL OR h.cost_model_key = s.snapshot_cost_model_key)
),

in_force AS (
  SELECT *
  FROM candidate
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY snapshot_key, cost_model_key, part_key, part_operation_key, cost_sub_type_key
    ORDER BY change_ts DESC, change_key DESC) = 1
)

SELECT
  i.snapshot_key                                        AS snapshot_key,
  i.snapshot_date                                       AS snapshot_date,
  COALESCE(s.snapshot_cost_model_key, i.cost_model_key) AS cost_model_key,
  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,
  i.cost_sub_type_key                                   AS cost_sub_type_key,
  i.cost                                                AS cost,
  i.change_date                                         AS cost_change_date,
  i.cost_source                                         AS cost_source,
  i.part_operation_key                                  AS part_operation_key
FROM in_force i
JOIN snap s
  ON s.snapshot_key = i.snapshot_key
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(p.Part_Key AS INT64) = i.part_key
