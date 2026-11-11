-- VoxScorecardsLive.vw_sc_last_month (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-01 14:15 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH params AS (
  SELECT DATE_SUB(DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH), INTERVAL 1 MONTH) AS last_month
),
goals AS (
  SELECT
    MAX(IF(LOWER(TRIM(metric)) = 'sales',   goal_value, NULL)) AS sales_goal,
    MAX(IF(LOWER(TRIM(metric)) = 'revenue', goal_value, NULL)) AS revenue_goal
  FROM `voxdatalake.PlexProd.v2_scorecard_goals_resolved`
  WHERE IFNULL(TRIM(scope), '') = ''
    AND period_month = (SELECT last_month FROM params)
)
SELECT
  w.month_start                                         AS last_month,
  w.revenue,
  g.revenue_goal,
  SAFE_DIVIDE(w.revenue, g.revenue_goal)                AS revenue_pct_to_goal,
  w.sales,
  g.sales_goal,
  SAFE_DIVIDE(w.sales, g.sales_goal)                    AS sales_pct_to_goal,
  w.encapsulation, w.encapsulation_goal,
  SAFE_DIVIDE(w.encapsulation, w.encapsulation_goal)    AS encapsulation_pct_to_goal,
  w.packaging      AS bottling, w.packaging_goal AS bottling_goal,
  SAFE_DIVIDE(w.packaging, w.packaging_goal)            AS bottling_pct_to_goal,
  w.labeling, w.labeling_goal,
  SAFE_DIVIDE(w.labeling, w.labeling_goal)              AS labeling_pct_to_goal,
  w.wip, w.inventory_value, w.oos_count
FROM `voxdatalake.VoxScorecardsLive.vw_sc_monthly_wide` w
CROSS JOIN goals g
WHERE w.month_start = (SELECT last_month FROM params)
