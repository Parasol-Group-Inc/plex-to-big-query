-- inventory_valuation_total_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/inventory_valuation_total_view.sql
-- confidence: medium
-- plex_views: Part_v_Snapshot, Part_v_Cost_Sub_Type_Breakdown_History, Part_v_Snapshot_Cost_Sub_Type_Breakdown, Part_v_Part, Part_v_Container, Part_v_Cost_Model
-- notes: inventory_valuation_summary_report inlined as CTEs; primary cost model only; stock = active containers except Receiving (Plex's Inventory Valuation screen); only the current snapshot has a value (earlier dates are NULL).
-- Translated 2026-10-20 from the BigQuery view; brought up to date 2026-10-30 (cost model, stock scope, counts). Not yet run in Plex SQL Developer.

-- GRAIN: one row per snapshot_date (the last snapshot taken that day).
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
),

-- inlined inventory_valuation_summary_report, primary cost model only
summary_all AS (
  SELECT
    pc.snapshot_key, pc.snapshot_date, pc.part_key, p.Part_No AS part_number,
    cm.cost_model_name, pc.op_unit_cost AS unit_cost,
    CASE WHEN pc.snapshot_key = ls.snapshot_key THEN 1 ELSE 0 END AS is_current_snapshot,
    CASE WHEN pc.snapshot_key = ls.snapshot_key THEN COALESCE(oh.on_hand_qty, 0) END AS on_hand_qty,
    CASE WHEN pc.snapshot_key = ls.snapshot_key THEN COALESCE(oh.on_hand_qty, 0) * pc.op_unit_cost END AS inventory_value,
    CASE WHEN pc.snapshot_key = ls.snapshot_key THEN COALESCE(av.on_hand_qty, 0) * pc.op_unit_cost END AS available_inventory_value
  FROM part_cost AS pc
  CROSS JOIN latest_snapshot AS ls
  JOIN cost_model AS cm ON cm.cost_model_key = pc.cost_model_key AND cm.is_primary = 1
  LEFT JOIN Part_v_Part AS p ON pc.part_key = p.Part_Key
  LEFT JOIN on_hand AS oh ON oh.part_key = pc.part_key
  LEFT JOIN available AS av ON av.part_key = pc.part_key
),

-- Plex can take more than one snapshot a day; keep only the last so values are not doubled
summary AS (
  SELECT sa.*
  FROM summary_all AS sa
  WHERE sa.snapshot_date IS NOT NULL
    AND sa.snapshot_key = (SELECT MAX(sb.snapshot_key) FROM summary_all AS sb WHERE sb.snapshot_date = sa.snapshot_date)
),

-- parts in stock today with no positive cost in the primary model (value missing, not zero)
uncosted AS (
  SELECT COUNT(*) AS uncosted_on_hand_part_count
  FROM on_hand AS oh
  WHERE oh.on_hand_qty > 0
    AND oh.part_key NOT IN (
          SELECT s.part_key FROM summary AS s
          WHERE s.is_current_snapshot = 1 AND s.part_key IS NOT NULL AND s.unit_cost > 0)
)

SELECT
  s.snapshot_date,
  MAX(s.cost_model_name)                                  AS cost_model_name,
  SUM(s.inventory_value)                                  AS total_inventory_value,
  SUM(s.available_inventory_value)                        AS available_inventory_value,
  COUNT(DISTINCT s.part_number)                           AS part_count,
  MAX(s.is_current_snapshot)                              AS is_current_snapshot,
  CASE WHEN MAX(s.is_current_snapshot) = 1
       THEN COUNT(DISTINCT CASE WHEN s.on_hand_qty > 0 AND s.unit_cost > 0 THEN s.part_key END) END AS valued_part_count,
  CASE WHEN MAX(s.is_current_snapshot) = 1
       THEN MAX(u.uncosted_on_hand_part_count) END        AS uncosted_on_hand_part_count
FROM summary AS s
CROSS JOIN uncosted AS u
GROUP BY s.snapshot_date
ORDER BY s.snapshot_date DESC;
