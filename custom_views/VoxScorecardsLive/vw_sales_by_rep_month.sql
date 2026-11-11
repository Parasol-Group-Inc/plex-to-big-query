-- VoxScorecardsLive.vw_sales_by_rep_month (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 16:57 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH monthly_sales AS (
  SELECT DATE_TRUNC(date_approved, MONTH) AS month, sales_rep, SUM(amount) AS actual_total
  FROM `voxdatalake.VoxScorecardsLive.vw_sales`
  WHERE sales_rep IS NOT NULL AND sales_rep != ''
  GROUP BY 1, 2
),
plex_goals AS (
  SELECT period_month AS month, TRIM(scope) AS sales_rep, CAST(goal_value AS INT64) AS goal
  FROM `voxdatalake.PlexProd.v2_scorecard_goals_resolved`
  WHERE LOWER(TRIM(metric)) = 'sales' AND IFNULL(TRIM(scope), '') != ''
),
may_goals AS (
  SELECT DATE '2026-05-01' AS month, 'Kami Butcher' AS sales_rep, 1800000 AS goal UNION ALL
  SELECT DATE '2026-05-01', 'Tyler Hall', 1500000 UNION ALL
  SELECT DATE '2026-05-01', 'Janet Pacheco', 500000 UNION ALL
  SELECT DATE '2026-05-01', 'Ruben Espinosa', 175000 UNION ALL
  SELECT DATE '2026-05-01', 'Landen Epperson', 150000 UNION ALL
  SELECT DATE '2026-05-01', 'Aishah Alqasim', 75000 UNION ALL
  SELECT DATE '2026-05-01', 'Zeljan Avdic', 0 UNION ALL
  SELECT DATE '2026-05-01', 'Sales Representative', 0
),
all_goals AS (
  SELECT month, sales_rep, goal FROM plex_goals
  UNION ALL
  SELECT m.month, m.sales_rep, m.goal FROM may_goals m
  WHERE NOT EXISTS (SELECT 1 FROM plex_goals p WHERE p.month = m.month AND p.sales_rep = m.sales_rep)
),
spine AS (
  SELECT month, sales_rep FROM all_goals
  UNION DISTINCT
  SELECT month, sales_rep FROM monthly_sales
)
SELECT
  sp.month, sp.sales_rep, g.goal, COALESCE(s.actual_total, 0) AS actual_total,
  IF(r.sales_rep IS NOT NULL AND r.active, 'Primary', 'Other') AS rep_type,   -- Primary = sales_rep_roster
  r.sort_order AS rep_sort
FROM spine sp
LEFT JOIN all_goals g     ON g.month = sp.month AND g.sales_rep = sp.sales_rep
LEFT JOIN monthly_sales s ON s.month = sp.month AND s.sales_rep = sp.sales_rep
LEFT JOIN `voxdatalake.VoxScorecardsLive.sales_rep_roster` r ON r.sales_rep = sp.sales_rep
ORDER BY sp.month, r.sort_order, sp.sales_rep
