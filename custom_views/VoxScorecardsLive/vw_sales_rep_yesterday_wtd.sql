-- VoxScorecardsLive.vw_sales_rep_yesterday_wtd (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 17:43 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH d AS (
  SELECT
    CURRENT_DATE('America/Denver') AS today,
    CASE WHEN EXTRACT(DAYOFWEEK FROM CURRENT_DATE('America/Denver')) = 2
         THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 3 DAY)
         ELSE DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY) END AS yday,
    DATE_TRUNC(CURRENT_DATE('America/Denver'), WEEK(MONDAY)) AS week_start,
    DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH) AS month_start
),
s AS (SELECT * FROM `voxdatalake.VoxScorecardsLive.vw_sales`),
agg AS (
  SELECT
    s.sales_rep,
    SUM(IF(s.date_approved = d.yday, s.amount, 0))                      AS sales_yesterday,
    COUNTIF(s.date_approved = d.yday)                                   AS orders_yesterday,
    SUM(IF(s.date_approved >= d.week_start, s.amount, 0))               AS sales_wtd,
    SUM(IF(s.date_approved >= d.month_start, s.amount, 0))              AS sales_mtd,
    ARRAY_AGG(IF(s.date_approved = d.yday, STRUCT(s.name AS customer, s.amount AS amount), NULL)
              IGNORE NULLS ORDER BY s.amount DESC LIMIT 1)[SAFE_OFFSET(0)] AS top_yday
  FROM s CROSS JOIN d
  WHERE s.date_approved >= LEAST(d.week_start, d.month_start, d.yday)
  GROUP BY s.sales_rep
)
SELECT
  r.sort_order AS rep_sort,
  r.sales_rep,
  (SELECT yday FROM d) AS yesterday_date,
  COALESCE(a.sales_yesterday, 0) AS sales_yesterday,
  COALESCE(a.orders_yesterday, 0) AS orders_yesterday,
  a.top_yday.customer AS top_customer_yesterday,
  a.top_yday.amount   AS top_order_yesterday,
  COALESCE(a.sales_wtd, 0) AS sales_wtd,
  COALESCE(a.sales_mtd, 0) AS sales_mtd
FROM `voxdatalake.VoxScorecardsLive.sales_rep_roster` r
LEFT JOIN agg a USING (sales_rep)
WHERE r.active
