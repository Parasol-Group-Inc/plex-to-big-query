-- bottling_job_open_with_orders_report — Plex SQL Developer equivalent (DIRECT links only)
-- plex_equivalent_of: reports/sql/bottling_job_open_with_orders_view.sql
-- confidence: medium
-- plex_views: Part_v_Job_Op, Part_v_Job, Part_v_Workcenter, Part_v_Part, Part_v_Job_Status, Part_v_Job_Type, Sales_v_Release_Job, Sales_v_Release, Sales_v_PO_Line, Sales_v_PO, Common_v_Customer
-- notes: Covers only the 'Direct' path (job created from an order release). The BigQuery view's
--   'Suggested' path reads sales_orders_report (a BigQuery view) and is not translated.
--   Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per open Bottling job and order it was created from.

SELECT DISTINCT
  j.Job_No                  AS job_no,
  p.Part_No                 AS part_no,
  p.Name                    AS part_name,
  jt.Job_Type               AS job_type,
  js.Job_Status             AS job_status,
  j.Quantity                AS qty_pending,
  CAST(j.Add_Date AS date)  AS date_entered,
  po.Order_No               AS order_no,
  c.Name                    AS customer
FROM Part_v_Job_Op AS jo
JOIN Part_v_Job AS j
  ON jo.Job_Key = j.Job_Key
JOIN Part_v_Workcenter AS wc
  ON jo.Workcenter_Key = wc.Workcenter_Key
LEFT JOIN Part_v_Part AS p
  ON j.Part_Key = p.Part_Key
LEFT JOIN Part_v_Job_Status AS js
  ON j.Job_Status_Key = js.Job_Status_Key
LEFT JOIN Part_v_Job_Type AS jt
  ON j.Job_Type_Key = jt.Job_Type_Key
LEFT JOIN Sales_v_Release_Job AS rj
  ON rj.Job_Key = j.Job_Key
LEFT JOIN Sales_v_Release AS rel
  ON rel.Release_Key = rj.Release_Key
LEFT JOIN Sales_v_PO_Line AS pl
  ON pl.PO_Line_Key = rel.PO_Line_Key
LEFT JOIN Sales_v_PO AS po
  ON po.PO_Key = pl.PO_Key
LEFT JOIN Common_v_Customer AS c
  ON c.Customer_No = po.Customer_No
WHERE wc.Workcenter_Group = 'Bottling'
  AND js.Completed_Status = 0
  AND js.Cancelled_Status = 0
  AND js.Hold_Status = 0
