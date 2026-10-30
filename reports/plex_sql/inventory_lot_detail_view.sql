-- inventory_lot_detail_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/inventory_lot_detail_view.sql
-- confidence: medium
-- plex_views: Part_v_Container, Part_v_Lot, Part_v_Lot_Shelf_Life, Part_v_Shelf_Life_Type, Part_v_Part, Part_v_Part_Product_Type, Part_v_Snapshot, Part_v_Cost_Sub_Type_Breakdown_History, Part_v_Snapshot_Cost_Sub_Type_Breakdown, Part_v_Cost_Model
-- notes: inventory_valuation_summary_report inlined as CTEs for the primary-model unit cost on the current snapshot. Best By = the Part_v_Lot_Shelf_Life date whose Part_v_Shelf_Life_Type has Best_By = 1 (key 327 at Vox). Days to Best By counted from GETDATE() (BigQuery uses today in America/Denver). Unverified in T-SQL.
-- Translated 2026-10-30 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per (part, lot, container status) over active containers.
-- SUM(inventory_value) WHERE in_valuation_total = 1 equals the valuation total;
-- WHERE is_available = 1 equals available_inventory_value.
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
,

summary_rows AS (
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
  ON av.part_key = pc.part_key
),

containers AS (
  SELECT c2.Part_Key AS part_key, c2.Lot_Key AS lot_key,
         UPPER(LTRIM(RTRIM(c2.Container_Status))) AS container_status, c2.Quantity AS quantity
  FROM Part_v_Container AS c2
  WHERE c2.Active = 1
),

by_lot_status AS (
  SELECT ct.part_key, ct.lot_key, ct.container_status,
         COUNT(*) AS container_count, SUM(ct.quantity) AS quantity
  FROM containers AS ct
  GROUP BY ct.part_key, ct.lot_key, ct.container_status
),

-- the lot date of the shelf-life type Plex flags as Best By
best_by AS (
  SELECT sl.Lot_Key AS lot_key, MIN(CAST(sl.Lot_Shelf_Life AS date)) AS best_by_date
  FROM Part_v_Lot_Shelf_Life AS sl
  JOIN Part_v_Shelf_Life_Type AS t ON t.Shelf_Life_Type_Key = sl.Shelf_Life_Type_Key
  WHERE t.Best_By = 1
  GROUP BY sl.Lot_Key
),

unit_cost AS (
  SELECT sr.part_key, MAX(sr.unit_cost) AS unit_cost
  FROM summary_rows AS sr
  WHERE sr.is_current_snapshot = 1 AND sr.is_primary_cost_model = 1
  GROUP BY sr.part_key
)

SELECT
  p2.Part_No                                            AS part_no,
  p2.Revision                                           AS revision,
  p2.Name                                               AS part_name,
  pt2.Product_Type                                      AS part_product_type,
  l.Lot_No                                              AS lot_no,
  b.container_status                                    AS container_status,
  b.container_count                                     AS container_count,
  b.quantity                                            AS quantity,
  uc.unit_cost                                          AS unit_cost,
  b.quantity * ISNULL(uc.unit_cost, 0)                  AS inventory_value,
  bb.best_by_date                                       AS best_by_date,
  DATEDIFF(day, CAST(GETDATE() AS date), bb.best_by_date) AS days_to_best_by,
  CASE WHEN YEAR(bb.best_by_date) >= 2200 THEN 1 ELSE 0 END AS best_by_is_placeholder,
  CASE WHEN b.container_status = 'EXPIRED' THEN 1 ELSE 0 END AS is_expired_status,
  CASE WHEN b.container_status IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
       THEN 1 ELSE 0 END                                AS is_available,
  CASE WHEN b.container_status <> 'RECEIVING' THEN 1 ELSE 0 END AS in_valuation_total,
  b.part_key                                            AS part_key,
  b.lot_key                                             AS lot_key
FROM by_lot_status AS b
LEFT JOIN Part_v_Part AS p2 ON p2.Part_Key = b.part_key
LEFT JOIN Part_v_Part_Product_Type AS pt2 ON pt2.Product_Type_Key = p2.Product_Type_Key
LEFT JOIN Part_v_Lot AS l ON l.Lot_Key = b.lot_key
LEFT JOIN best_by AS bb ON bb.lot_key = b.lot_key
LEFT JOIN unit_cost AS uc ON uc.part_key = b.part_key;
