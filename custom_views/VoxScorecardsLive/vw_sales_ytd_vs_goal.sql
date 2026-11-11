-- VoxScorecardsLive.vw_sales_ytd_vs_goal (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 15:49 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH monthly_goals AS (
  SELECT period_month AS month, CAST(goal_value AS INT64) AS goal
  FROM `voxdatalake.PlexProd.v2_scorecard_goals_resolved`
  WHERE LOWER(TRIM(metric)) = 'sales' AND IFNULL(TRIM(scope), '') = ''
    AND EXTRACT(YEAR FROM period_month) = 2026
),
monthly_sales AS (
  SELECT DATE_TRUNC(date_approved, MONTH) AS month, SUM(amount) AS actual_total
  FROM `voxdatalake.VoxScorecardsLive.vw_sales` GROUP BY 1
)
SELECT g.month, g.goal, COALESCE(s.actual_total, 0) AS actual_total
FROM monthly_goals g LEFT JOIN monthly_sales s ON g.month = s.month
ORDER BY g.month
