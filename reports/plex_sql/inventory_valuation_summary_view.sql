-- inventory_valuation_summary_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/inventory_valuation_summary_view.sql
-- confidence: medium
-- plex_views: Part_v_Snapshot, Part_v_Cost_Sub_Type_Breakdown_History, Part_v_Snapshot_Cost_Sub_Type_Breakdown, Part_v_Part, Part_v_Container, Part_v_Cost_Model
-- notes: on-hand = active containers except Receiving (2026-10-30; was the Vox availability rule); QUALIFY with WINDOW translated literally (rank 1 by cost must also sit on the part's latest change date, else the part drops out, as in BigQuery). Unverified in T-SQL.
-- Translated 2026-10-20 from the BigQuery view; cost model columns added 2026-10-30. Not yet run in Plex SQL Developer.

-- GRAIN: one row per (snapshot, cost model, part).
-- RULE: unit cost = SUM of cost sub-types per operation; part cost = highest operation cost among
--       operations costed on the part's latest cost-change date. Quantity/value only on the latest snapshot.
WITH snap AS (
  SELECT
    s.Snapshot_Key                  AS snapshot_key,
    CAST(s.Snapshot_Date AS date)   AS snapshot_date,
    s.Cost_Model_Key                AS snapshot_cost_model_key   -- NULL on real snapshots
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
    h.Change_Date                   AS change_ts
  FROM Part_v_Cost_Sub_Type_Breakdown_History AS h
),

ptr AS (
  SELECT p.Snapshot_Key AS snapshot_key, p.Change_Key AS change_key
  FROM Part_v_Snapshot_Cost_Sub_Type_Breakdown AS p
),

candidate AS (
  SELECT s.snapshot_key, s.snapshot_date, 'snapshot pointer' AS cost_source,
         h.change_key, h.cost_model_key, h.part_key, h.part_operation_key,
         h.cost_sub_type_key, h.cost, h.change_date, h.change_ts
  FROM snap AS s
  JOIN ptr AS pt ON pt.snapshot_key = s.snapshot_key
  JOIN hist AS h ON h.change_key = pt.change_key
  WHERE s.snapshot_cost_model_key IS NULL OR h.cost_model_key = s.snapshot_cost_model_key

  UNION ALL

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
  SELECT r.* FROM ranked AS r WHERE r.rn = 1
),

-- (b) one cost per operation = sum of its cost sub-types
op_cost AS (
  SELECT
    i.snapshot_key, i.snapshot_date, i.cost_source, i.cost_model_key, i.part_key, i.part_operation_key,
    SUM(i.cost)         AS op_unit_cost,
    COUNT(*)            AS cost_sub_type_count,
    MAX(i.change_date)  AS op_change_date
  FROM in_force AS i
  GROUP BY i.snapshot_key, i.snapshot_date, i.cost_source, i.cost_model_key, i.part_key, i.part_operation_key
),

-- (c) part cost = highest operation cost, kept only if on the part's latest cost-change date
part_cost_ranked AS (
  SELECT
    oc.*,
    COUNT(*) OVER (PARTITION BY oc.snapshot_key, oc.cost_model_key, oc.part_key) AS operation_count,
    MAX(oc.op_change_date) OVER (PARTITION BY oc.snapshot_key, oc.cost_model_key, oc.part_key) AS max_change_date,
    ROW_NUMBER() OVER (
      PARTITION BY oc.snapshot_key, oc.cost_model_key, oc.part_key
      ORDER BY oc.op_unit_cost DESC, oc.part_operation_key DESC) AS rn
  FROM op_cost AS oc
),

part_cost AS (
  SELECT r.*
  FROM part_cost_ranked AS r
  WHERE r.op_change_date = r.max_change_date AND r.rn = 1
),

latest_snapshot AS (
  SELECT MAX(s.snapshot_key) AS snapshot_key
  FROM snap AS s
  WHERE s.snapshot_date = (SELECT MAX(s2.snapshot_date) FROM snap AS s2)
),

-- one row per cost model; the total reads the one Plex marks Primary_Model (bit, so <> 0)
cost_model AS (
  SELECT
    m.Cost_Model_Key                AS cost_model_key,
    m.Cost_Model                    AS cost_model_name,
    CASE WHEN m.Primary_Model <> 0 THEN 1 ELSE 0 END AS is_primary
  FROM Part_v_Cost_Model AS m
),

-- stock on the books as Plex's Inventory Valuation screen counts it (2026-10-30):
-- every active container except Receiving, not the Vox availability rule
on_hand AS (
  SELECT c.Part_Key AS part_key, SUM(c.Quantity) AS on_hand_qty
  FROM Part_v_Container AS c
  WHERE c.Active = 1
    AND UPPER(LTRIM(RTRIM(c.Container_Status))) <> 'RECEIVING'
  GROUP BY c.Part_Key
),
-- available stock only (2026-10-30): part_on_hand_inventory_report's Vox rule, inlined
available AS (
  SELECT c.Part_Key AS part_key, SUM(c.Quantity) AS on_hand_qty
  FROM Part_v_Container AS c
  WHERE c.Active = 1
    AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  GROUP BY c.Part_Key
)

SELECT
  pc.snapshot_key                                       AS snapshot_key,
  pc.snapshot_date                                      AS snapshot_date,
  pc.cost_model_key                                     AS cost_model_key,
  cm.cost_model_name                                    AS cost_model_name,
  COALESCE(cm.is_primary, 0)                            AS is_primary_cost_model,
  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,
  pc.op_unit_cost                                       AS total_cost,
  pc.cost_sub_type_count                                AS cost_sub_type_count,
  pc.part_key                                           AS part_key,
  pc.op_unit_cost                                       AS unit_cost,
  pc.part_operation_key                                 AS costed_operation_key,
  pc.operation_count                                    AS operation_count,
  pc.op_change_date                                     AS cost_change_date,
  pc.cost_source                                        AS cost_source,
  CASE WHEN pc.snapshot_key = ls.snapshot_key THEN 1 ELSE 0 END AS is_current_snapshot,
  -- on-hand is today's, so only attached to the current snapshot
  CASE WHEN pc.snapshot_key = ls.snapshot_key THEN COALESCE(oh.on_hand_qty, 0) END AS on_hand_qty,
  CASE WHEN pc.snapshot_key = ls.snapshot_key THEN COALESCE(oh.on_hand_qty, 0) * pc.op_unit_cost END AS inventory_value,
  CASE WHEN pc.snapshot_key = ls.snapshot_key THEN COALESCE(av.on_hand_qty, 0) END AS available_on_hand_qty,
  CASE WHEN pc.snapshot_key = ls.snapshot_key THEN COALESCE(av.on_hand_qty, 0) * pc.op_unit_cost END AS available_inventory_value
FROM part_cost AS pc
CROSS JOIN latest_snapshot AS ls
LEFT JOIN cost_model AS cm
  ON cm.cost_model_key = pc.cost_model_key
LEFT JOIN Part_v_Part AS p
  ON pc.part_key = p.Part_Key
LEFT JOIN on_hand AS oh
  ON oh.part_key = pc.part_key
LEFT JOIN available AS av
  ON av.part_key = pc.part_key;
