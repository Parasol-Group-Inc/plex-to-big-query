-- shipping_revenue_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/shipping_revenue_report.sql
-- confidence: high
-- plex_views: Sales_v_Shipper, Sales_v_Shipper_Line, Sales_v_Shipper_Status, Sales_v_Shipper_AR_Invoice, Accounting_v_AR_Invoice, Sales_v_Release, Sales_v_PO_Line, Sales_v_PO, Common_v_Customer, Part_v_Part, Part_v_Part_Group
-- notes: Grain: one row per shipper line; revenue = quantity x price (ignores shipment_price_override, as in BigQuery).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
-- 2026-10-29: order_no, po_no, invoice_no added, as in BigQuery.

SELECT
  s.Shipper_No                                          AS shipper_no,
  po.Order_No                                           AS order_no,
  po.PO_No                                              AS po_no,
  ar.Invoice_No                                         AS invoice_no,
  CAST(s.Ship_Date AS date)                             AS ship_date,
  CAST(inv.Add_Date AS date)                            AS invoice_date,
  cust.Name                                             AS customer_name,
  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,
  pgrp.Part_Group                                       AS part_group,
  sl.Quantity                                           AS quantity_shipped,
  sl.Price                                              AS price,
  sl.Shipment_Price                                     AS shipment_price_override,
  sl.Quantity * sl.Price                                AS shipping_revenue
FROM Sales_v_Shipper AS s
JOIN Sales_v_Shipper_Line AS sl ON s.Shipper_Key = sl.Shipper_Key
JOIN Sales_v_Shipper_Status AS ss ON s.Shipper_Status_Key = ss.Shipper_Status_Key
LEFT JOIN Sales_v_Shipper_AR_Invoice AS inv ON sl.Shipper_Line_Key = inv.Shipper_Line_Key
LEFT JOIN Accounting_v_AR_Invoice AS ar ON inv.Invoice_Link = ar.Invoice_Link
LEFT JOIN Sales_v_Release AS rel ON sl.Release_Key = rel.Release_Key
LEFT JOIN Sales_v_PO_Line AS pol ON rel.PO_Line_Key = pol.PO_Line_Key
LEFT JOIN Sales_v_PO AS po ON pol.PO_Key = po.PO_Key
LEFT JOIN Common_v_Customer AS cust ON s.Customer_No = cust.Customer_No
LEFT JOIN Part_v_Part AS p ON sl.Part_Key = p.Part_Key
LEFT JOIN Part_v_Part_Group AS pgrp ON p.Part_Group_Key = pgrp.Part_Group_Key
-- Only shipments whose status is flagged Shipped
WHERE ss.Shipped = 1
ORDER BY invoice_date DESC;
