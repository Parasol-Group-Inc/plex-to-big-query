-- sales_orders_over_10k_bottles_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_orders_over_10k_bottles_view.sql
-- confidence: medium
-- plex_views: Sales_v_PO, Sales_v_PO_Status, Sales_v_PO_Line, Sales_v_Release, Common_v_Customer
-- notes: STRING_AGG(DISTINCT) is not allowed in T-SQL; rewritten as DISTINCT subquery then STRING_AGG (needs SQL Server 2017+; unit order is alphabetical).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

WITH
qty_totals AS (
  -- Total quantity per order across all releases
  SELECT
    pol.PO_Key,
    SUM(rel.Quantity) AS total_quantity
  FROM Sales_v_PO_Line AS pol
  LEFT JOIN Sales_v_Release AS rel ON pol.PO_Line_Key = rel.PO_Line_Key
  GROUP BY pol.PO_Key
),
unit_list AS (
  -- Distinct quantity units per order, comma-joined
  SELECT d.PO_Key, STRING_AGG(d.Quantity_Unit, ', ') WITHIN GROUP (ORDER BY d.Quantity_Unit) AS quantity_units
  FROM (
    SELECT DISTINCT pol.PO_Key, rel.Quantity_Unit
    FROM Sales_v_PO_Line AS pol
    JOIN Sales_v_Release AS rel ON pol.PO_Line_Key = rel.PO_Line_Key
    WHERE rel.Quantity_Unit IS NOT NULL
  ) AS d
  GROUP BY d.PO_Key
)
SELECT
  po.Order_No                                           AS order_no,
  po.PO_No                                              AS document_so,
  CAST(po.PO_Date AS date)                              AS date_created,
  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS status,
  po.Customer_No,
  cust.Name                                             AS customer_name,
  qt.total_quantity,
  ul.quantity_units                                     AS quantity_units_seen
FROM Sales_v_PO AS po
JOIN qty_totals AS qt ON po.PO_Key = qt.PO_Key
LEFT JOIN unit_list AS ul ON po.PO_Key = ul.PO_Key
LEFT JOIN Sales_v_PO_Status AS sts ON po.PO_Status_Key = sts.PO_Status_Key
LEFT JOIN Common_v_Customer AS cust ON po.Customer_No = cust.Customer_No
-- 10,000+ units on the order
WHERE qt.total_quantity >= 10000;
