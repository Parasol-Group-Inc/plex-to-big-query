-- VoxScorecardsLive.vw_sales_mtd_vs_goal (view), backed up from BigQuery by scripts/backup_custom_views.py
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
),
days_in_month AS (
  SELECT month,
    DATE_DIFF(DATE_ADD(month, INTERVAL 1 MONTH), month, DAY) AS total_days,
    CASE WHEN month = DATE_TRUNC(CURRENT_DATE(), MONTH)
         THEN GREATEST(0, DATE_DIFF(DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY), month, DAY))
         ELSE DATE_DIFF(DATE_ADD(month, INTERVAL 1 MONTH), month, DAY) END AS days_elapsed
  FROM monthly_goals
)
SELECT g.month, g.goal, COALESCE(s.actual_total, 0) AS actual_total,
  ROUND(COALESCE(s.actual_total, 0) / NULLIF(g.goal, 0), 4) AS goal_progress,
  ROUND(d.days_elapsed / d.total_days, 4) AS pct_into_month
FROM monthly_goals g
LEFT JOIN monthly_sales s ON g.month = s.month
LEFT JOIN days_in_month d ON g.month = d.month
ORDER BY g.month
