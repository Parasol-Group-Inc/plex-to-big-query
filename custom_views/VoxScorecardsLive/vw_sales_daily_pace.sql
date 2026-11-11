-- VoxScorecardsLive.vw_sales_daily_pace (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 18:45 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH d AS (
  SELECT
    CURRENT_DATE('America/Denver') AS today,
    CASE WHEN EXTRACT(DAYOFWEEK FROM CURRENT_DATE('America/Denver')) = 2
         THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 3 DAY)
         ELSE DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY) END AS yday,
    DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH) AS month_start,
    LAST_DAY(CURRENT_DATE('America/Denver')) AS month_end
),
cal AS (
  SELECT day FROM d, UNNEST(GENERATE_DATE_ARRAY(d.month_start, d.month_end)) AS day
  WHERE EXTRACT(DAYOFWEEK FROM day) BETWEEN 2 AND 6
),
goal AS (
  SELECT goal_value AS monthly_goal
  FROM `voxdatalake.PlexProd.v2_scorecard_goals_resolved`, d
  WHERE LOWER(TRIM(metric)) = 'sales' AND IFNULL(TRIM(scope), '') = '' AND period_month = d.month_start
  QUALIFY ROW_NUMBER() OVER (ORDER BY updated_at DESC) = 1
),
wk AS (
  SELECT DATE_TRUNC(yday, WEEK(MONDAY)) AS week_start FROM d
),
sales AS (
  SELECT
    SUM(IF(s.date_approved = d.yday, s.amount, 0)) AS sales_yesterday,
    SUM(IF(s.date_approved BETWEEN wk.week_start AND d.yday, s.amount, 0)) AS sales_wtd,
    SUM(IF(s.date_approved BETWEEN d.month_start AND d.yday, s.amount, 0)) AS sales_mtd_thru_yday
  FROM `voxdatalake.VoxScorecardsLive.vw_sales` s, d, wk
),
last10 AS (
  SELECT * FROM `voxdatalake.VoxScorecardsLive.vw_sales`, d
  WHERE date_approved BETWEEN DATE_SUB(d.today, INTERVAL 9 DAY) AND d.today
),
top_order AS (
  SELECT name AS customer, sales_rep, amount, date_approved
  FROM last10 ORDER BY amount DESC LIMIT 1
),
top_rep AS (
  SELECT sales_rep, SUM(amount) AS amount
  FROM last10 WHERE IFNULL(sales_rep, '') != ''
  GROUP BY 1 ORDER BY 2 DESC LIMIT 1
)
SELECT
  d.yday AS yesterday_date,
  g.monthly_goal,
  (SELECT COUNT(*) FROM cal) AS workdays_in_month,
  SAFE_DIVIDE(g.monthly_goal, (SELECT COUNT(*) FROM cal)) AS daily_goal,
  s.sales_yesterday,
  SAFE_DIVIDE(s.sales_yesterday, SAFE_DIVIDE(g.monthly_goal, (SELECT COUNT(*) FROM cal))) AS yesterday_pct_to_daily_goal,
  (SELECT COUNT(*) FROM cal, wk WHERE day BETWEEN wk.week_start AND d.yday) AS workdays_wtd,
  SAFE_DIVIDE(g.monthly_goal, (SELECT COUNT(*) FROM cal))
    * (SELECT COUNT(*) FROM cal, wk WHERE day BETWEEN wk.week_start AND d.yday) AS wtd_goal,
  s.sales_wtd,
  SAFE_DIVIDE(s.sales_wtd, SAFE_DIVIDE(g.monthly_goal, (SELECT COUNT(*) FROM cal))
    * (SELECT COUNT(*) FROM cal, wk WHERE day BETWEEN wk.week_start AND d.yday)) AS wtd_pct_to_goal,
  (SELECT COUNT(*) FROM cal WHERE day <= d.yday) AS workdays_mtd,
  SAFE_DIVIDE(g.monthly_goal, (SELECT COUNT(*) FROM cal)) * (SELECT COUNT(*) FROM cal WHERE day <= d.yday) AS mtd_pace_goal,
  s.sales_mtd_thru_yday,
  (SELECT customer FROM top_order) AS top_order_10d_customer,
  (SELECT sales_rep FROM top_order) AS top_order_10d_rep,
  (SELECT amount FROM top_order) AS top_order_10d_amount,
  (SELECT date_approved FROM top_order) AS top_order_10d_date,
  (SELECT sales_rep FROM top_rep) AS top_rep_10d,
  (SELECT amount FROM top_rep) AS top_rep_10d_amount
FROM d CROSS JOIN sales s LEFT JOIN goal g ON TRUE
