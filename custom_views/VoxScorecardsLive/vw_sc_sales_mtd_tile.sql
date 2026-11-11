-- VoxScorecardsLive.vw_sc_sales_mtd_tile (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-01 14:03 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH params AS (SELECT DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH) AS this_month),
mtd AS (
  SELECT COALESCE(SUM(sales_value), 0) AS sales_mtd, COUNT(DISTINCT order_no) AS orders_mtd
  FROM `voxdatalake.PlexProd.sales_mtd_by_status_change_report`
  WHERE sales_month = (SELECT this_month FROM params)
),
goal AS (
  SELECT goal_value AS sales_goal
  FROM `voxdatalake.PlexProd.v2_scorecard_goals_resolved`
  WHERE LOWER(TRIM(metric)) = 'sales'
    AND IFNULL(TRIM(scope), '') = ''
    AND period_month = (SELECT this_month FROM params)
  QUALIFY ROW_NUMBER() OVER (ORDER BY updated_at DESC) = 1
),
prior AS (
  SELECT SUM(value) AS sales_prior_months
  FROM `voxdatalake.VoxScorecardsLive.scorecard_monthly_history`
  WHERE metric = 'sales'
    AND EXTRACT(YEAR FROM month_start) = EXTRACT(YEAR FROM (SELECT this_month FROM params))
    AND month_start < (SELECT this_month FROM params)
)
SELECT
  (SELECT this_month FROM params)              AS sales_month,
  m.sales_mtd,
  g.sales_goal,
  SAFE_DIVIDE(m.sales_mtd, g.sales_goal)       AS pct_to_goal,
  m.orders_mtd,
  CAST(COALESCE(p.sales_prior_months, 0) AS FLOAT64) AS sales_prior_months,
  CAST(COALESCE(p.sales_prior_months, 0) AS FLOAT64) + m.sales_mtd AS sales_ytd
FROM mtd m CROSS JOIN prior p LEFT JOIN goal g ON TRUE
