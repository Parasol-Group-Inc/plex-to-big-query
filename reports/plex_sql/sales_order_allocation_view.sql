-- sales_order_allocation_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_order_allocation_view.sql
-- confidence: high
-- plex_views: Sales_v_PO, Sales_v_PO_Line, Sales_v_Release, Sales_v_Release_Job, Part_v_Job, Part_v_Job_Status, Sales_v_PO_Status, Common_v_Customer, Part_v_Part
-- notes: Grain: one row per release x linked job. Part_v_Job/Part_v_Job_Status come from the work_orders pipeline (no filters).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

SELECT
  po.PO_No                                              AS document_so,
  sts.PO_Status                                         AS so_status,
  po.Customer_No,
  cust.Name                                             AS customer_name,
  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,
  rel.Quantity                                          AS qty_allocated,
  rel.Quantity_Unit                                     AS qty_unit,
  j.Job_No                                              AS job_no,
  js.Job_Status                                         AS job_status,
  j.Quantity                                            AS job_qty,
  j.Due_Date                                            AS job_due_date
FROM Sales_v_PO AS po
JOIN Sales_v_PO_Line AS pol ON po.PO_Key = pol.PO_Key
JOIN Sales_v_Release AS rel ON pol.PO_Line_Key = rel.PO_Line_Key
JOIN Sales_v_Release_Job AS rj ON rel.Release_Key = rj.Release_Key
JOIN Part_v_Job AS j ON rj.Job_Key = j.Job_Key
LEFT JOIN Sales_v_PO_Status AS sts ON po.PO_Status_Key = sts.PO_Status_Key
LEFT JOIN Common_v_Customer AS cust ON po.Customer_No = cust.Customer_No
LEFT JOIN Part_v_Part AS p ON pol.Part_Key = p.Part_Key
LEFT JOIN Part_v_Job_Status AS js ON j.Job_Status_Key = js.Job_Status_Key
-- Order not cancelled/closed, and the job is not completed, cancelled or on hold
WHERE po.PO_Status_Key NOT IN (2074, 2076)
  AND ISNULL(CAST(js.Completed_Status AS int), 0) = 0
  AND ISNULL(CAST(js.Cancelled_Status AS int), 0) = 0
  AND ISNULL(CAST(js.Hold_Status AS int), 0) = 0;
