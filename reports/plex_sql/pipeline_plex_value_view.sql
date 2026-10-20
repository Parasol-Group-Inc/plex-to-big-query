-- pipeline_plex_value_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/pipeline_plex_value_view.sql
-- confidence: high
-- plex_views: Sales_v_PO, Sales_v_PO_Line, Sales_v_Release, Sales_v_PO_Status, Sales_v_Order_Salesperson, Sales_v_Price, Part_v_Customer_Part_Price, Common_v_Customer, Plexus_Control_v_Plexus_User, Part_v_Part
-- notes: Mechanical translation; CONCAT replaced by + so a missing name stays NULL; booleans become 1/0; no extraction filters apply.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Open pipeline value: quotes, plus orders in status 2585 (Pending Sales Approval); cancelled statuses excluded.
-- Rep precedence: inside sales on the order, then customer's assigned user, then first order salesperson.
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
rep1 AS (
  -- primary salesperson on the order
  SELECT osp.PO_Key, osp.Plexus_User_No, osp.Commission
  FROM Sales_v_Order_Salesperson AS osp
  WHERE osp.Sort_Order = 1
)
SELECT
  CASE WHEN ISNULL(sts.Is_Quote, 0) = 1 THEN 'Quote' ELSE 'Pending Sales Approval' END AS pipeline_stage,
  po.PO_No                                              AS document_so,
  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS so_status,
  NULLIF(CAST(po.PO_Date AS date), '1970-01-01')        AS date_created,
  cust.Name                                             AS customer_name,
  COALESCE(ui.First_Name + ' ' + ui.Last_Name,
           ua.First_Name + ' ' + ua.Last_Name,
           u1.First_Name + ' ' + u1.Last_Name)          AS sales_rep,
  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,
  rel.Quantity                                          AS qty_quoted,
  ISNULL(lp.Price, bp.Price)                            AS price_ea,
  CASE WHEN lp.Price IS NULL AND bp.Price IS NOT NULL THEN 1 ELSE 0 END AS price_from_fallback_list,
  ISNULL(lp.Price, bp.Price) * rel.Quantity             AS pipeline_value
FROM Sales_v_PO AS po
JOIN Sales_v_PO_Line AS pol ON po.PO_Key = pol.PO_Key
JOIN Sales_v_Release AS rel ON pol.PO_Line_Key = rel.PO_Line_Key
JOIN Sales_v_PO_Status AS sts ON po.PO_Status_Key = sts.PO_Status_Key
LEFT JOIN Common_v_Customer AS cust ON po.Customer_No = cust.Customer_No
LEFT JOIN rep1 AS rep1 ON po.PO_Key = rep1.PO_Key
LEFT JOIN Plexus_Control_v_Plexus_User AS u1 ON rep1.Plexus_User_No = u1.Plexus_User_No
LEFT JOIN Plexus_Control_v_Plexus_User AS ui ON po.Inside_Sales = ui.Plexus_User_No
LEFT JOIN Plexus_Control_v_Plexus_User AS ua ON cust.Assigned_To = ua.Plexus_User_No
LEFT JOIN Part_v_Part AS p ON pol.Part_Key = p.Part_Key
LEFT JOIN line_price AS lp ON pol.PO_Line_Key = lp.PO_Line_Key
LEFT JOIN base_price AS bp ON pol.Customer_Part_Key = bp.Customer_Part_Key
WHERE (ISNULL(sts.Is_Quote, 0) = 1 OR po.PO_Status_Key = 2585)
  AND ISNULL(sts.Cancelled_Status, 0) = 0
ORDER BY CASE WHEN ISNULL(sts.Is_Quote, 0) = 1 THEN 'Quote' ELSE 'Pending Sales Approval' END,
         NULLIF(CAST(po.PO_Date AS date), '1970-01-01') DESC
