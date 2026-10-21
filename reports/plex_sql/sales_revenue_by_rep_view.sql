-- sales_revenue_by_rep_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_revenue_by_rep_view.sql
-- confidence: high
-- plex_views: Sales_v_PO, Sales_v_PO_Line, Sales_v_Release, Sales_v_Order_Salesperson, Sales_v_Price, Common_v_Customer, Plexus_Control_v_Plexus_User, Part_v_Customer_Part_Price
-- notes: Grain: one row per order; no status filter (as in BigQuery). Unassigned orders get key -1.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

WITH
line_price AS (
  -- One price per PO line: primary price first, then lowest breakpoint, then newest effective date
  SELECT x.PO_Line_Key, x.Price
  FROM (
    SELECT
      pr.PO_Line_Key,
      pr.Price,
      ROW_NUMBER() OVER (
        PARTITION BY pr.PO_Line_Key
        ORDER BY ISNULL(CAST(pr.Primary_Price AS int), 0) DESC,
                 pr.Breakpoint_Quantity ASC,
                 pr.Effective_Date DESC
      ) AS rn
    FROM Sales_v_Price AS pr
    WHERE ISNULL(CAST(pr.Active AS int), 1) <> 0
  ) AS x
  WHERE x.rn = 1
),
base_price AS (
  -- Fallback price: lowest-breakpoint price per customer part
  SELECT x.Customer_Part_Key, x.Price
  FROM (
    SELECT
      cpp.Customer_Part_Key,
      cpp.Price,
      ROW_NUMBER() OVER (
        PARTITION BY cpp.Customer_Part_Key
        ORDER BY cpp.Breakpoint_Quantity ASC
      ) AS rn
    FROM Part_v_Customer_Part_Price AS cpp
  ) AS x
  WHERE x.rn = 1
),
order_totals AS (
  -- Computed order total = sum of (line price x release qty)
  SELECT
    pol.PO_Key,
    SUM(COALESCE(lp.Price, bp.Price) * rel.Quantity) AS order_total_computed
  FROM Sales_v_PO_Line AS pol
  LEFT JOIN Sales_v_Release AS rel ON pol.PO_Line_Key = rel.PO_Line_Key
  LEFT JOIN base_price AS bp ON pol.Customer_Part_Key = bp.Customer_Part_Key
  LEFT JOIN line_price AS lp ON lp.PO_Line_Key = pol.PO_Line_Key
  GROUP BY pol.PO_Key
),
rep1 AS (
  -- Primary rep = Sort_Order 1
  SELECT os.PO_Key, os.Plexus_User_No
  FROM Sales_v_Order_Salesperson AS os
  WHERE os.Sort_Order = 1
)
SELECT
  COALESCE(u.Plexus_User_No, -1)                        AS sales_rep_key,
  COALESCE(u.First_Name + ' ' + u.Last_Name, 'Unassigned') AS sales_rep_name,
  po.PO_No                                              AS document_so,
  po.Customer_No,
  cust.Name                                             AS customer_name,
  ot.order_total_computed
FROM Sales_v_PO AS po
LEFT JOIN order_totals AS ot ON po.PO_Key = ot.PO_Key
LEFT JOIN rep1 ON po.PO_Key = rep1.PO_Key
LEFT JOIN Plexus_Control_v_Plexus_User AS u ON rep1.Plexus_User_No = u.Plexus_User_No
LEFT JOIN Common_v_Customer AS cust ON po.Customer_No = cust.Customer_No;
