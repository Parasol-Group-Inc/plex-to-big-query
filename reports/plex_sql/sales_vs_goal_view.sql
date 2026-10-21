-- sales_vs_goal_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_vs_goal_view.sql
-- confidence: low
-- plex_views: Sales_v_PO, Sales_v_PO_Change, Sales_v_PO_Line, Sales_v_Release, Sales_v_PO_Status, Sales_v_PO_Type, Sales_v_Order_Salesperson, Sales_v_Price, Part_v_Customer_Part_Price, Common_v_Customer, Plexus_Control_v_Plexus_User, Part_v_Part, Part_v_Part_Group
-- notes: Goals come from BigQuery scorecard_goals_resolved (not in Plex): replaced by an empty placeholder CTE, so goal columns are NULL; actual sales are the same as BigQuery.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Monthly sales (by rep) vs goal. Goal scope is an exact string match to the rep name; blank scope = company-wide row.
WITH
first_pending_fulfillment AS (
  -- sales date = first time the order reached Pending Fulfillment (status 2073)
  SELECT
    pc.PO_Key,
    MIN(NULLIF(CAST(pc.Change_Date AS date), '1970-01-01')) AS sales_date
  FROM Sales_v_PO_Change AS pc
  WHERE pc.PO_Status_Key = 2073
  GROUP BY pc.PO_Key
),
rep1 AS (
  -- primary salesperson on the order
  SELECT osp.PO_Key, osp.Plexus_User_No, osp.Commission
  FROM Sales_v_Order_Salesperson AS osp
  WHERE osp.Sort_Order = 1
),
rep2 AS (
  SELECT osp2.PO_Key, osp2.Plexus_User_No
  FROM Sales_v_Order_Salesperson AS osp2
  WHERE osp2.Sort_Order = 2
),
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
mtd AS (
SELECT
  fpf.sales_date                                        AS sales_date,
  DATEFROMPARTS(YEAR(fpf.sales_date), MONTH(fpf.sales_date), 1) AS sales_month,
  YEAR(fpf.sales_date)                                  AS sales_year,
  po.PO_No                                              AS document_so,
  sts.PO_Status                                         AS current_status,
  typ.PO_Type                                           AS order_type,
  cust.Name                                             AS customer_name,
  COALESCE(
    ui.First_Name + ' ' + ui.Last_Name,
    ua.First_Name + ' ' + ua.Last_Name,
    u1.First_Name + ' ' + u1.Last_Name
  )                                                     AS sales_rep,
  CASE
    WHEN ui.Plexus_User_No IS NOT NULL THEN 'order'
    WHEN ua.Plexus_User_No IS NOT NULL THEN 'customer'
    WHEN u1.Plexus_User_No IS NOT NULL THEN 'order_salesperson'
  END                                                   AS sales_rep_source,
  u2.First_Name + ' ' + u2.Last_Name                    AS sales_rep_2,
  rep1.Commission                                       AS commission_pct,
  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,
  pgrp.Part_Group                                       AS part_group,
  rel.Quantity                                          AS qty_sold,
  ISNULL(lp.Price, bp.Price)                            AS price_ea,
  CASE WHEN lp.Price IS NULL AND bp.Price IS NOT NULL THEN 1 ELSE 0 END AS price_from_fallback_list,
  ISNULL(lp.Price, bp.Price) * rel.Quantity             AS sales_value
FROM Sales_v_PO AS po
JOIN first_pending_fulfillment AS fpf ON po.PO_Key = fpf.PO_Key
JOIN Sales_v_PO_Line AS pol ON po.PO_Key = pol.PO_Key
JOIN Sales_v_Release AS rel ON pol.PO_Line_Key = rel.PO_Line_Key
LEFT JOIN Sales_v_PO_Status AS sts ON po.PO_Status_Key = sts.PO_Status_Key
LEFT JOIN Sales_v_PO_Type AS typ ON po.PO_Type_Key = typ.PO_Type_Key
LEFT JOIN Common_v_Customer AS cust ON po.Customer_No = cust.Customer_No
LEFT JOIN rep1 AS rep1 ON po.PO_Key = rep1.PO_Key
LEFT JOIN rep2 AS rep2 ON po.PO_Key = rep2.PO_Key
LEFT JOIN Plexus_Control_v_Plexus_User AS u1 ON rep1.Plexus_User_No = u1.Plexus_User_No
LEFT JOIN Plexus_Control_v_Plexus_User AS u2 ON rep2.Plexus_User_No = u2.Plexus_User_No
LEFT JOIN Plexus_Control_v_Plexus_User AS ui ON po.Inside_Sales = ui.Plexus_User_No
LEFT JOIN Plexus_Control_v_Plexus_User AS ua ON cust.Assigned_To = ua.Plexus_User_No
LEFT JOIN Part_v_Part AS p ON pol.Part_Key = p.Part_Key
LEFT JOIN Part_v_Part_Group AS pgrp ON p.Part_Group_Key = pgrp.Part_Group_Key
LEFT JOIN line_price AS lp ON pol.PO_Line_Key = lp.PO_Line_Key
LEFT JOIN base_price AS bp ON pol.Customer_Part_Key = bp.Customer_Part_Key
WHERE fpf.sales_date IS NOT NULL
),
sales_summary AS (
  -- sales_mtd_summary_report
  SELECT
    m.sales_month,
    ISNULL(m.sales_rep, '(no rep assigned)') AS sales_rep,
    COUNT(DISTINCT m.document_so)            AS order_count,
    SUM(m.qty_sold)                          AS qty_sold,
    SUM(m.sales_value)                       AS sales_value
  FROM mtd AS m
  WHERE m.sales_month IS NOT NULL
  GROUP BY m.sales_month, ISNULL(m.sales_rep, '(no rep assigned)')
),
goals_resolved AS (
  -- PLACEHOLDER: goals are typed by people in BigQuery (scorecard_goals_app / scorecard_goals); Plex has no
  -- equivalent. This CTE is empty, so every goal column below comes back NULL. Replace with real goals to test.
  SELECT
    CAST(NULL AS varchar(100))  AS metric,
    CAST(NULL AS date)          AS period_month,
    CAST(NULL AS varchar(200))  AS scope,
    CAST(NULL AS float)         AS goal_value,
    CAST(NULL AS varchar(500))  AS note
  WHERE 1 = 0
),
actual AS (
  SELECT
    ss.sales_month,
    ss.sales_rep,
    SUM(ss.sales_value) AS actual_sales,
    SUM(ss.qty_sold)    AS qty_sold,
    SUM(ss.order_count) AS order_count
  FROM sales_summary AS ss
  GROUP BY ss.sales_month, ss.sales_rep
),
goal AS (
  SELECT
    gr.period_month,
    CASE WHEN gr.scope IS NULL OR gr.scope = '' THEN '(company-wide)' ELSE gr.scope END AS sales_rep,
    SUM(gr.goal_value) AS goal_value,
    MAX(gr.note)       AS goal_note
  FROM goals_resolved AS gr
  WHERE LOWER(gr.metric) = 'sales'
  GROUP BY gr.period_month, CASE WHEN gr.scope IS NULL OR gr.scope = '' THEN '(company-wide)' ELSE gr.scope END
)
SELECT
  COALESCE(a.sales_month, g.period_month)                    AS sales_month,
  COALESCE(a.sales_rep, g.sales_rep)                         AS sales_rep,
  ISNULL(a.actual_sales, 0)                                  AS actual_sales,
  ISNULL(a.qty_sold, 0)                                      AS qty_sold,
  ISNULL(a.order_count, 0)                                   AS order_count,
  g.goal_value                                               AS goal_value,
  ISNULL(a.actual_sales, 0) / NULLIF(g.goal_value, 0)        AS pct_to_goal,
  ISNULL(a.actual_sales, 0) - g.goal_value                   AS variance_to_goal,
  CASE WHEN a.sales_rep IS NULL THEN 1 ELSE 0 END            AS goal_without_sales,
  CASE WHEN g.sales_rep IS NULL THEN 1 ELSE 0 END            AS sales_without_goal,
  g.goal_note                                                AS goal_note
FROM actual AS a
FULL OUTER JOIN goal AS g
  ON a.sales_month = g.period_month
 AND a.sales_rep   = g.sales_rep
ORDER BY COALESCE(a.sales_month, g.period_month) DESC, ISNULL(a.actual_sales, 0) DESC
