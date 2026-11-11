-- VoxScorecardsLive.vw_sc_revenue_mtd_tile (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-09 16:01 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH params AS (
  SELECT DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH) AS this_month,
         CURRENT_DATE('America/Denver') AS today
),
adj AS (  -- discounts etc. posted to 4xxxx accounts other than 40200 (vw_sc_revenue_adjustments)
  SELECT COALESCE(SUM(amount), 0) AS adj_mtd
  FROM `voxdatalake.VoxScorecardsLive.vw_sc_revenue_adjustments`
  WHERE DATE_TRUNC(ship_date, MONTH) = (SELECT this_month FROM params)
),
mtd AS (
  SELECT COALESCE(SUM(shipping_revenue), 0) + (SELECT adj_mtd FROM adj) AS revenue_mtd,
         COALESCE(SUM(units_shipped), 0) AS units_shipped_mtd
  FROM `voxdatalake.PlexProd.sales_revenue_summary_report`
  WHERE revenue_month = (SELECT this_month FROM params)
),
goal AS (
  SELECT goal_value AS revenue_goal, note AS goal_note
  FROM `voxdatalake.PlexProd.v2_scorecard_goals_resolved`
  WHERE LOWER(TRIM(metric)) = 'revenue'
    AND IFNULL(TRIM(scope), '') = ''
    AND period_month = (SELECT this_month FROM params)
  QUALIFY ROW_NUMBER() OVER (ORDER BY updated_at DESC) = 1
),
prior AS (
  SELECT SUM(value) AS revenue_prior_months
  FROM `voxdatalake.VoxScorecardsLive.scorecard_monthly_history`
  WHERE metric = 'revenue'
    AND EXTRACT(YEAR FROM month_start) = EXTRACT(YEAR FROM (SELECT this_month FROM params))
    AND month_start < (SELECT this_month FROM params)
)
SELECT
  (SELECT this_month FROM params)                AS revenue_month,
  m.revenue_mtd,
  g.revenue_goal,
  SAFE_DIVIDE(m.revenue_mtd, g.revenue_goal)     AS pct_to_goal,
  SAFE_DIVIDE(EXTRACT(DAY FROM (SELECT today FROM params)) - 1,
              EXTRACT(DAY FROM LAST_DAY((SELECT today FROM params)))) AS pct_into_month,
  m.units_shipped_mtd,
  CAST(COALESCE(p.revenue_prior_months, 0) AS FLOAT64)                 AS revenue_prior_months,
  CAST(COALESCE(p.revenue_prior_months, 0) AS FLOAT64) + m.revenue_mtd AS revenue_ytd,
  g.goal_note,
  (SELECT adj_mtd FROM adj)                      AS revenue_adjustments_mtd
FROM mtd m CROSS JOIN prior p LEFT JOIN goal g ON TRUE
