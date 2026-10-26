-- approaching_msl_report — Plex SQL Developer equivalent (Plex-side figures only)
-- plex_equivalent_of: reports/sql/approaching_msl_view.sql
-- confidence: low
-- plex_views: Part_v_Part, Part_v_Container, Part_v_Production, Part_v_BOM, Part_v_Job, Part_v_Job_Status
-- notes: Covers reorder point, on hand, Plex usage (90 days) and open job quantity. NOT in Plex: NetSuite usage and reorder point (manual-data app tables msl_item_inputs / msl_rules), quantity_available (demand from inventory_available_to_sell_report) and on_order_qty (purchasing_open_orders_report). Not yet run in Plex SQL Developer.

-- GRAIN: one row per part with a reorder point or recorded usage.
WITH usage AS (
  SELECT
    b.Component_Part_Key AS Part_Key,
    SUM(pr.Quantity * b.Quantity) AS qty_used
  FROM Part_v_Production AS pr
  JOIN Part_v_BOM AS b
    ON b.Part_Operation_Key = pr.Part_Operation_Key
  WHERE ISNULL(pr.Rejected, 0) = 0
    AND ISNULL(b.Active, 1) <> 0
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
)

SELECT
  p.Part_No AS part_no,
  p.Name AS description,
  p.Minimum_Inventory_Quantity AS reorder_point,
  oh.on_hand_qty,
  u.qty_used * 1.0 / NULLIF(s.usage_days, 0) AS avg_daily_usage,
  s.usage_days,
  oh.on_hand_qty / NULLIF(u.qty_used * 1.0 / NULLIF(s.usage_days, 0), 0) AS days_on_hand,
  ISNULL(oj.open_job_qty, 0) AS open_job_qty
FROM Part_v_Part AS p
CROSS JOIN span AS s
LEFT JOIN usage AS u ON u.Part_Key = p.Part_Key
LEFT JOIN on_hand AS oh ON oh.Part_Key = p.Part_Key
LEFT JOIN open_jobs AS oj ON oj.Part_Key = p.Part_Key
WHERE p.Minimum_Inventory_Quantity > 0 OR u.qty_used > 0
