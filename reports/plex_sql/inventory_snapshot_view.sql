-- inventory_snapshot_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/inventory_snapshot_view.sql
-- confidence: high
-- plex_views: Part_v_Snapshot, Part_v_Cost_Sub_Type_Breakdown_History, Part_v_Snapshot_Cost_Sub_Type_Breakdown, Part_v_Part
-- notes: Mechanical translation; QUALIFY rewritten as ROW_NUMBER in a CTE. Pointer table is empty in real Plex so the as-of-snapshot-date fallback produces the rows.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per (snapshot, cost model, part, operation, cost sub-type).
WITH snap AS (
  SELECT
    s.Snapshot_Key                  AS snapshot_key,
    CAST(s.Snapshot_Date AS date)   AS snapshot_date,
    s.Cost_Model_Key                AS snapshot_cost_model_key   -- NULL on real snapshots; filter only when set
  FROM Part_v_Snapshot AS s
),

-- source column is "Change_key" (lowercase k) on this view
hist AS (
  SELECT
    h.Change_key                    AS change_key,
    h.Cost_Model_Key                AS cost_model_key,
    h.Part_Key                      AS part_key,
    h.Part_Operation_Key            AS part_operation_key,
    h.Cost_Sub_Type_Key             AS cost_sub_type_key,
    h.Cost                          AS cost,
    CAST(h.Change_Date AS date)     AS change_date,
    h.Change_Date                   AS change_ts   -- orders two changes on the same day
  FROM Part_v_Cost_Sub_Type_Breakdown_History AS h
),

ptr AS (
  SELECT p.Snapshot_Key AS snapshot_key, p.Change_Key AS change_key
  FROM Part_v_Snapshot_Cost_Sub_Type_Breakdown AS p
),

candidate AS (
  -- Plex's own membership, for snapshots that have pointer rows
  SELECT s.snapshot_key, s.snapshot_date, 'snapshot pointer' AS cost_source,
         h.change_key, h.cost_model_key, h.part_key, h.part_operation_key,
         h.cost_sub_type_key, h.cost, h.change_date, h.change_ts
  FROM snap AS s
  JOIN ptr AS pt ON pt.snapshot_key = s.snapshot_key
  JOIN hist AS h ON h.change_key = pt.change_key
  WHERE s.snapshot_cost_model_key IS NULL OR h.cost_model_key = s.snapshot_cost_model_key

  UNION ALL

  -- as-of fallback, for snapshots with no pointer rows
  SELECT s.snapshot_key, s.snapshot_date, 'cost history as of snapshot date' AS cost_source,
         h.change_key, h.cost_model_key, h.part_key, h.part_operation_key,
         h.cost_sub_type_key, h.cost, h.change_date, h.change_ts
  FROM snap AS s
  JOIN hist AS h ON h.change_date <= s.snapshot_date
  WHERE s.snapshot_key NOT IN (SELECT pn.snapshot_key FROM ptr AS pn WHERE pn.snapshot_key IS NOT NULL)
    AND (s.snapshot_cost_model_key IS NULL OR h.cost_model_key = s.snapshot_cost_model_key)
),

ranked AS (
  SELECT c.*,
         ROW_NUMBER() OVER (
           PARTITION BY c.snapshot_key, c.cost_model_key, c.part_key, c.part_operation_key, c.cost_sub_type_key
           ORDER BY c.change_ts DESC, c.change_key DESC) AS rn
  FROM candidate AS c
),

in_force AS (
  SELECT r.* FROM ranked AS r WHERE r.rn = 1   -- latest row per key
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
FROM in_force AS i
JOIN snap AS s
  ON s.snapshot_key = i.snapshot_key
LEFT JOIN Part_v_Part AS p
  ON p.Part_Key = i.part_key;
