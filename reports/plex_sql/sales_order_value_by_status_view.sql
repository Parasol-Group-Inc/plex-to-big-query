-- sales_order_value_by_status_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_order_value_by_status_view.sql
-- confidence: high
-- plex_views: Sales_v_PO, Sales_v_PO_Line, Sales_v_Release, Sales_v_PO_Status, Sales_v_Price, Part_v_Customer_Part_Price, Sales_v_Shipper_Line_Release, Sales_v_Shipper_Line, Sales_v_Shipper, Sales_v_Shipper_Status, Common_v_Customer, Part_v_Part
-- notes: Mechanical translation; booleans become 1/0 and GREATEST becomes CASE; no extraction filters apply.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- WIP = open order line (status counted in MRP) whose release has no shipped shipper yet.
-- status_key 2073 = Pending Fulfillment, 2075 = On Hold.
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
),
release_shipped AS (
  SELECT DISTINCT slr.Release_Key
  FROM Sales_v_Shipper_Line_Release AS slr
  JOIN Sales_v_Shipper_Line AS sl ON slr.Shipper_Line_Key = sl.Shipper_Line_Key
  JOIN Sales_v_Shipper AS s ON sl.Shipper_Key = s.Shipper_Key
  JOIN Sales_v_Shipper_Status AS ss ON s.Shipper_Status_Key = ss.Shipper_Status_Key
  WHERE ss.Shipped = 1
)
SELECT
  po.Order_No                                           AS order_no,
  po.PO_No                                              AS document_so,
  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS so_status,
  CASE WHEN po.PO_Status_Key = 2073 THEN 1 ELSE 0 END   AS is_pending_fulfillment,
  CASE WHEN po.PO_Status_Key = 2075 THEN 1 ELSE 0 END   AS is_on_hold,
  0                                                     AS also_counts_in_pipeline,
  cust.Name                                             AS customer_name,
  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,
  rel.Release_Key                                       AS release_key,
  q.qty_pending                                         AS qty_pending,
  ISNULL(lp.Price, bp.Price)                            AS price_ea,
  CASE WHEN lp.Price IS NULL AND bp.Price IS NOT NULL THEN 1 ELSE 0 END AS price_from_fallback_list,
  ISNULL(lp.Price, bp.Price) * q.qty_pending            AS wip_value
FROM Sales_v_PO AS po
JOIN Sales_v_PO_Line AS pol ON po.PO_Key = pol.PO_Key
JOIN Sales_v_Release AS rel ON pol.PO_Line_Key = rel.PO_Line_Key
CROSS APPLY (
  SELECT CASE WHEN rel.Quantity - ISNULL(rel.Quantity_Shipped, 0) > 0
              THEN rel.Quantity - ISNULL(rel.Quantity_Shipped, 0) ELSE 0 END AS qty_pending
) AS q
LEFT JOIN Sales_v_PO_Status AS sts ON po.PO_Status_Key = sts.PO_Status_Key
LEFT JOIN Common_v_Customer AS cust ON po.Customer_No = cust.Customer_No
LEFT JOIN Part_v_Part AS p ON pol.Part_Key = p.Part_Key
LEFT JOIN line_price AS lp ON pol.PO_Line_Key = lp.PO_Line_Key
LEFT JOIN base_price AS bp ON pol.Customer_Part_Key = bp.Customer_Part_Key
LEFT JOIN release_shipped AS rs ON rel.Release_Key = rs.Release_Key
WHERE ISNULL(sts.Include_In_MRP, 0) = 1
  AND rs.Release_Key IS NULL
