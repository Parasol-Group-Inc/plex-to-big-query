-- sales_orders_aging_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_orders_aging_view.sql
-- confidence: high
-- plex_views: Sales_v_PO, Sales_v_PO_Type, Sales_v_PO_Status, Sales_v_PO_Line, Sales_v_Release, Sales_v_Order_Salesperson, Sales_v_Price, Common_v_Customer, Plexus_Control_v_Plexus_User, Part_v_Part, Part_v_Customer_Part_Price
-- notes: Rep names use + (NULL if either name is NULL) to match BigQuery CONCAT; pipeline extractions have no filters. Orders at least 14 days old and not cancelled/closed (2074, 2076).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

WITH
rep1 AS (
  -- Primary rep = Sort_Order 1
  SELECT os.PO_Key, os.Plexus_User_No
  FROM Sales_v_Order_Salesperson AS os
  WHERE os.Sort_Order = 1
),
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
orders AS (
  SELECT po.*, CAST(po.PO_Date AS date) AS order_date
  FROM Sales_v_PO AS po
)
SELECT
  o.Order_No                                            AS order_no,
  o.PO_No                                               AS document_so,
  o.order_date                                          AS date_created,
  DATEDIFF(day, o.order_date, CAST(GETDATE() AS date))  AS days_old,
  typ.PO_Type                                           AS order_type,
  o.PO_Status_Key                                       AS status_key,
  sts.PO_Status                                         AS status,
  o.Customer_No,
  cust.Name                                             AS customer_name,
  u1.First_Name + ' ' + u1.Last_Name                    AS sales_rep_1,
  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,
  rel.Quantity                                          AS qty_ordered,
  COALESCE(lp.Price, bp.Price) * rel.Quantity           AS price_total
FROM orders AS o
LEFT JOIN Sales_v_PO_Type AS typ ON o.PO_Type_Key = typ.PO_Type_Key
LEFT JOIN Sales_v_PO_Status AS sts ON o.PO_Status_Key = sts.PO_Status_Key
LEFT JOIN Common_v_Customer AS cust ON o.Customer_No = cust.Customer_No
LEFT JOIN rep1 ON o.PO_Key = rep1.PO_Key
LEFT JOIN Plexus_Control_v_Plexus_User AS u1 ON rep1.Plexus_User_No = u1.Plexus_User_No
LEFT JOIN Sales_v_PO_Line AS pol ON o.PO_Key = pol.PO_Key
LEFT JOIN Sales_v_Release AS rel ON pol.PO_Line_Key = rel.PO_Line_Key
LEFT JOIN Part_v_Part AS p ON pol.Part_Key = p.Part_Key
LEFT JOIN base_price AS bp ON pol.Customer_Part_Key = bp.Customer_Part_Key
LEFT JOIN line_price AS lp ON lp.PO_Line_Key = pol.PO_Line_Key
-- Not cancelled/closed, and at least 14 days old
WHERE o.PO_Status_Key NOT IN (2074, 2076)
  AND o.order_date <= DATEADD(day, -14, CAST(GETDATE() AS date));
