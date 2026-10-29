-- approaching_msl_report — Plex SQL Developer equivalent (Plex-side figures only)
-- plex_equivalent_of: reports/sql/approaching_msl_view.sql
-- confidence: low
-- plex_views: Part_v_Part, Part_v_Container, Part_v_Production, Part_v_BOM, Part_v_Job, Part_v_Job_Status, Purchasing_v_PO, Purchasing_v_PO_Status, Purchasing_v_Line_Item, Purchasing_v_Release
-- notes: Covers reorder point, on hand, Plex usage (90 days), open jobs and on order, one row per part number with wrapper keys converted (2026-10-28). NOT in Plex: NetSuite usage and reorder point (manual-data app tables msl_item_inputs / msl_rules) and quantity_available (demand from inventory_available_to_sell_report). Not yet run in Plex SQL Developer.

-- GRAIN: one row per part number with a reorder point or recorded usage.
-- Wrapper keys: a second Part_Key of the same part number whose BOM is one line pointing at
-- the stocked key; the line's Quantity converts the wrapper's unit (e.g. 0.001 for grams).
WITH wrap AS (
  SELECT b.Part_Key AS wrapper_key, b.Component_Part_Key AS root_key, MAX(b.Quantity) AS factor
  FROM Part_v_BOM AS b
  JOIN Part_v_Part AS pw ON pw.Part_Key = b.Part_Key
  JOIN Part_v_Part AS pc ON pc.Part_Key = b.Component_Part_Key
  WHERE pw.Part_No = pc.Part_No
    AND pw.Part_Key <> pc.Part_Key
    AND ISNULL(b.Active, 1) <> 0
    AND b.Quantity > 0
  GROUP BY b.Part_Key, b.Component_Part_Key
),

-- Production into a wrapper is skipped; the wrapper's own consumption is counted instead.
usage AS (
  SELECT
    b.Component_Part_Key AS Part_Key,
    SUM(pr.Quantity * b.Quantity) AS qty_used
  FROM Part_v_Production AS pr
  JOIN Part_v_BOM AS b
    ON b.Part_Operation_Key = pr.Part_Operation_Key
  LEFT JOIN wrap AS w
    ON w.wrapper_key = b.Part_Key AND w.root_key = b.Component_Part_Key
  WHERE ISNULL(pr.Rejected, 0) = 0
    AND ISNULL(b.Active, 1) <> 0
    AND w.wrapper_key IS NULL
    AND CAST(pr.Report_Date AS date) >= DATEADD(day, -89, CAST(GETDATE() AS date))
  GROUP BY b.Component_Part_Key
),

span AS (
  SELECT
    DATEDIFF(day, MIN(CAST(pr.Report_Date AS date)), MAX(CAST(pr.Report_Date AS date))) + 1 AS usage_days
  FROM Part_v_Production AS pr
  WHERE ISNULL(pr.Rejected, 0) = 0
    AND CAST(pr.Report_Date AS date) >= DATEADD(day, -89, CAST(GETDATE() AS date))
),

on_hand AS (
  SELECT c.Part_Key AS Part_Key, SUM(c.Quantity) AS on_hand_qty
  FROM Part_v_Container AS c
  WHERE c.Active = 1
    AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  GROUP BY c.Part_Key
),

open_jobs AS (
  SELECT j.Part_Key AS Part_Key, SUM(j.Quantity) AS open_job_qty
  FROM Part_v_Job AS j
  JOIN Part_v_Job_Status AS js
    ON js.Job_Status_Key = j.Job_Status_Key
  WHERE ISNULL(js.Completed_Status, 0) = 0
    AND ISNULL(js.Cancelled_Status, 0) = 0
    AND ISNULL(js.Hold_Status, 0) = 0
  GROUP BY j.Part_Key
),

on_order AS (
  SELECT li.Part_Key AS Part_Key, SUM(rel.Quantity) AS on_order_qty
  FROM Purchasing_v_PO AS po
  LEFT JOIN Purchasing_v_PO_Status AS sts ON sts.PO_Status_Key = po.PO_Status_Key
  JOIN Purchasing_v_Line_Item AS li ON li.PO_Key = po.PO_Key
  JOIN Purchasing_v_Release AS rel ON rel.Line_Item_Key = li.Line_Item_Key
  WHERE ISNULL(sts.Cancelled_Status, 0) = 0
    AND ISNULL(sts.Received, 0) = 0
    AND ISNULL(rel.Release_Status, '') <> 'Received'
  GROUP BY li.Part_Key
),

inv AS (
  SELECT
    p.Part_No AS part_no,
    MAX(CASE WHEN w.wrapper_key IS NULL THEN p.Name END) AS description,
    MAX(CASE WHEN w.wrapper_key IS NULL THEN p.Part_Type END) AS part_type,
    MAX(CASE WHEN w.wrapper_key IS NULL THEN p.Part_Group_Key END) AS part_group_key,
    MAX(CASE WHEN w.wrapper_key IS NULL THEN p.Part_Source_Key END) AS part_source_key,
    MAX(p.Minimum_Inventory_Quantity * ISNULL(w.factor, 1)) AS reorder_point,
    SUM(ISNULL(oh.on_hand_qty, 0) * ISNULL(w.factor, 1)) AS on_hand_qty,
    SUM(u.qty_used * ISNULL(w.factor, 1)) AS qty_used,
    SUM(ISNULL(oj.open_job_qty, 0) * ISNULL(w.factor, 1)) AS open_job_qty,
    SUM(ISNULL(oo.on_order_qty, 0) * ISNULL(w.factor, 1)) AS on_order_qty
  FROM Part_v_Part AS p
  LEFT JOIN wrap AS w ON w.wrapper_key = p.Part_Key
  LEFT JOIN usage AS u ON u.Part_Key = p.Part_Key
  LEFT JOIN on_hand AS oh ON oh.Part_Key = p.Part_Key
  LEFT JOIN open_jobs AS oj ON oj.Part_Key = p.Part_Key
  LEFT JOIN on_order AS oo ON oo.Part_Key = p.Part_Key
  GROUP BY p.Part_No
)

SELECT
  i.part_no,
  i.description,
  i.reorder_point,
  i.on_hand_qty,
  i.qty_used * 1.0 / NULLIF(s.usage_days, 0) AS avg_daily_usage,
  s.usage_days,
  i.on_hand_qty / NULLIF(i.qty_used * 1.0 / NULLIF(s.usage_days, 0), 0) AS days_on_hand,
  i.on_order_qty,
  i.open_job_qty,
  i.part_type,
  i.part_group_key,
  pg.Part_Group AS part_group,
  i.part_source_key
FROM inv AS i
CROSS JOIN span AS s
LEFT JOIN Part_v_Part_Group AS pg ON pg.Part_Group_Key = i.part_group_key
WHERE i.reorder_point > 0 OR i.qty_used > 0
