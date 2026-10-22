-- revenue_vs_goal_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/revenue_vs_goal_view.sql
-- confidence: low
-- plex_views: Sales_v_Shipper, Sales_v_Shipper_Line, Sales_v_Shipper_Status, Part_v_Part, Part_v_Part_Group
-- notes: Goals come from BigQuery scorecard_goals_resolved (not in Plex): replaced by an empty placeholder CTE, so goal columns are NULL; actuals are the same as BigQuery.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Monthly shipped revenue vs company-wide revenue goal (goal rows with no scope).
WITH
shipping_revenue AS (
  -- shipping_revenue_report: one row per shipped shipper line
  SELECT
    NULLIF(CAST(s.Ship_Date AS date), '1970-01-01') AS ship_date,
    pgrp.Part_Group                                 AS part_group,
    sl.Quantity                                     AS quantity_shipped,
    sl.Quantity * sl.Price                          AS shipping_revenue
  FROM Sales_v_Shipper AS s
  JOIN Sales_v_Shipper_Line AS sl ON s.Shipper_Key = sl.Shipper_Key
  JOIN Sales_v_Shipper_Status AS ss ON s.Shipper_Status_Key = ss.Shipper_Status_Key
  LEFT JOIN Part_v_Part AS p ON sl.Part_Key = p.Part_Key
  LEFT JOIN Part_v_Part_Group AS pgrp ON p.Part_Group_Key = pgrp.Part_Group_Key
  WHERE ss.Shipped = 1
),
revenue_summary AS (
  -- sales_revenue_summary_report: month x part group
  SELECT
    DATEFROMPARTS(YEAR(sr.ship_date), MONTH(sr.ship_date), 1) AS revenue_month,
    ISNULL(sr.part_group, '(no group)')                       AS part_group,
    COUNT(*)                                                  AS shipment_line_count,
    SUM(sr.quantity_shipped)                                  AS units_shipped,
    SUM(sr.shipping_revenue)                                  AS shipping_revenue
  FROM shipping_revenue AS sr
  WHERE sr.ship_date IS NOT NULL
  GROUP BY DATEFROMPARTS(YEAR(sr.ship_date), MONTH(sr.ship_date), 1), ISNULL(sr.part_group, '(no group)')
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
    rs.revenue_month,
    SUM(rs.shipping_revenue) AS actual_revenue,
    SUM(rs.units_shipped)    AS units_shipped
  FROM revenue_summary AS rs
  GROUP BY rs.revenue_month
),
goal AS (
  SELECT
    gr.period_month,
    SUM(gr.goal_value) AS goal_value,
    MAX(gr.note)       AS goal_note
  FROM goals_resolved AS gr
  WHERE LOWER(gr.metric) = 'revenue'
    AND (gr.scope IS NULL OR gr.scope = '')
  GROUP BY gr.period_month
)
SELECT
  a.revenue_month                                                  AS revenue_month,
  a.actual_revenue                                                 AS actual_revenue,
  a.units_shipped                                                  AS units_shipped,
  g.goal_value                                                     AS goal_value,
  a.actual_revenue / NULLIF(g.goal_value, 0)                       AS pct_to_goal,
  a.actual_revenue - g.goal_value                                  AS variance_to_goal,
  g.goal_note                                                      AS goal_note
FROM actual AS a
LEFT JOIN goal AS g ON a.revenue_month = g.period_month
ORDER BY a.revenue_month DESC
