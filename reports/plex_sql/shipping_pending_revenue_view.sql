-- shipping_pending_revenue_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/shipping_pending_revenue_view.sql
-- confidence: high
-- plex_views: Sales_v_Shipper, Sales_v_Shipper_Line, Sales_v_Shipper_Status, Sales_v_Shipper_Line_Release, Sales_v_Release, Sales_v_PO_Line, Sales_v_PO, Sales_v_PO_Type, Sales_v_Price, Part_v_Customer_Part_Price, Common_v_Customer, Part_v_Part
-- notes: Mechanical translation; booleans become 1/0; no extraction filters apply.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Revenue sitting in shipping: shipper lines not yet shipped and not cancelled.
-- Price precedence: shipper line price, then order line price, then customer list price.
WITH
line_price AS (
  -- one price per order line: primary price first, then lowest breakpoint, then newest effective date
  SELECT x.PO_Line_Key, x.Price
  FROM (
    SELECT
      pr.PO_Line_Key,
      pr.Price,
      ROW_NUMBER() OVER (
        PARTITION BY pr.PO_Line_Key
        ORDER BY ISNULL(pr.Primary_Price, 0) DESC, pr.Breakpoint_Quantity ASC, pr.Effective_Date DESC
      ) AS rn
    FROM Sales_v_Price AS pr
    WHERE ISNULL(pr.Active, 1) <> 0
  ) AS x
  WHERE x.rn = 1
),
base_price AS (
  -- customer list price fallback: lowest breakpoint per customer part
  SELECT y.Customer_Part_Key, y.Price
  FROM (
    SELECT
      cpp.Customer_Part_Key,
      cpp.Price,
      ROW_NUMBER() OVER (PARTITION BY cpp.Customer_Part_Key ORDER BY cpp.Breakpoint_Quantity ASC) AS rn
    FROM Part_v_Customer_Part_Price AS cpp
  ) AS y
  WHERE y.rn = 1
)
SELECT
  s.Shipper_No                                          AS shipper_no,
  ss.Shipper_Status                                     AS shipper_status,
  cust.Name                                             AS customer_name,
  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,
  sl.Quantity                                           AS qty_ready,
  sl.Price                                              AS shipper_line_price,
  bp.Price                                              AS customer_price_fallback,
  lp.Price                                              AS order_line_price,
  COALESCE(NULLIF(sl.Price, 0), lp.Price, bp.Price)     AS effective_price,
  CASE
    WHEN NULLIF(sl.Price, 0) IS NOT NULL THEN 'shipper'
    WHEN lp.Price IS NOT NULL            THEN 'order_line'
    WHEN bp.Price IS NOT NULL            THEN 'customer_list'
  END                                                   AS price_source,
  sl.Quantity * COALESCE(NULLIF(sl.Price, 0), lp.Price, bp.Price) AS ready_value,
  CASE WHEN potype.Blanket = 1 THEN 1 ELSE 0 END        AS is_blanket_order
FROM Sales_v_Shipper AS s
JOIN Sales_v_Shipper_Line AS sl ON s.Shipper_Key = sl.Shipper_Key
JOIN Sales_v_Shipper_Status AS ss ON s.Shipper_Status_Key = ss.Shipper_Status_Key
LEFT JOIN Common_v_Customer AS cust ON s.Customer_No = cust.Customer_No
LEFT JOIN Part_v_Part AS p ON sl.Part_Key = p.Part_Key
LEFT JOIN base_price AS bp ON sl.Customer_Part_Key = bp.Customer_Part_Key
LEFT JOIN Sales_v_Shipper_Line_Release AS slr ON sl.Shipper_Line_Key = slr.Shipper_Line_Key
LEFT JOIN Sales_v_Release AS rel ON slr.Release_Key = rel.Release_Key
LEFT JOIN Sales_v_PO_Line AS pol ON rel.PO_Line_Key = pol.PO_Line_Key
LEFT JOIN line_price AS lp ON pol.PO_Line_Key = lp.PO_Line_Key
LEFT JOIN Sales_v_PO AS po ON pol.PO_Key = po.PO_Key
LEFT JOIN Sales_v_PO_Type AS potype ON po.PO_Type_Key = potype.PO_Type_Key
WHERE ISNULL(ss.Shipped, 0) <> 1
  AND ISNULL(ss.Cancel_Status, 0) <> 1
