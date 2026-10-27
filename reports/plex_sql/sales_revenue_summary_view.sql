-- sales_revenue_summary_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_revenue_summary_view.sql
-- confidence: high
-- plex_views: Sales_v_Shipper, Sales_v_Shipper_Line, Sales_v_Shipper_Status, Sales_v_Shipper_AR_Invoice, Common_v_Customer, Part_v_Part, Part_v_Part_Group
-- notes: BigQuery view reads shipping_revenue_report; that logic is inlined as a CTE. Monthly by part group.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

WITH shipping_revenue AS (
  SELECT
    s.Shipper_No                                          AS shipper_no,
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
  LEFT JOIN Common_v_Customer AS cust ON s.Customer_No = cust.Customer_No
  LEFT JOIN Part_v_Part AS p ON sl.Part_Key = p.Part_Key
  LEFT JOIN Part_v_Part_Group AS pgrp ON p.Part_Group_Key = pgrp.Part_Group_Key
  -- Only shipments whose status is flagged Shipped
  WHERE ss.Shipped = 1
)
SELECT
  DATEFROMPARTS(YEAR(sr.ship_date), MONTH(sr.ship_date), 1) AS revenue_month,
  COALESCE(sr.part_group, '(no group)')                  AS part_group,
  COUNT(*)                                               AS shipment_line_count,
  SUM(sr.quantity_shipped)                               AS units_shipped,
  SUM(sr.shipping_revenue)                               AS shipping_revenue
FROM shipping_revenue AS sr
WHERE sr.ship_date IS NOT NULL
GROUP BY DATEFROMPARTS(YEAR(sr.ship_date), MONTH(sr.ship_date), 1), COALESCE(sr.part_group, '(no group)')
ORDER BY revenue_month DESC, shipping_revenue DESC;
