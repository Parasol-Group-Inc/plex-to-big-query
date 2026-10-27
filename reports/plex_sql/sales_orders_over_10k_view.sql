-- sales_orders_over_10k_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_orders_over_10k_view.sql
-- confidence: high
-- plex_views: Sales_v_PO, Sales_v_PO_Status, Sales_v_PO_Line, Sales_v_Release, Sales_v_Price, Common_v_Customer, Part_v_Customer_Part_Price
-- notes: Grain: one row per order with computed total >= 10000; no status filter (as in BigQuery).
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
line_totals AS (
  -- Computed order total = sum of (line price x release qty)
  SELECT
    pol.PO_Key,
    SUM(COALESCE(lp.Price, bp.Price) * rel.Quantity) AS order_total_computed
  FROM Sales_v_PO_Line AS pol
  LEFT JOIN Sales_v_Release AS rel ON pol.PO_Line_Key = rel.PO_Line_Key
  LEFT JOIN base_price AS bp ON pol.Customer_Part_Key = bp.Customer_Part_Key
  LEFT JOIN line_price AS lp ON lp.PO_Line_Key = pol.PO_Line_Key
  GROUP BY pol.PO_Key
)
SELECT
  po.Order_No                                           AS order_no,
  po.PO_No                                              AS document_so,
  CAST(po.PO_Date AS date)                              AS date_created,
  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS status,
  po.Customer_No,
  cust.Name                                             AS customer_name,
  lt.order_total_computed,
  po.Master_Price                                       AS order_total_master_price
FROM Sales_v_PO AS po
JOIN line_totals AS lt ON po.PO_Key = lt.PO_Key
LEFT JOIN Sales_v_PO_Status AS sts ON po.PO_Status_Key = sts.PO_Status_Key
LEFT JOIN Common_v_Customer AS cust ON po.Customer_No = cust.Customer_No
WHERE lt.order_total_computed >= 10000;
