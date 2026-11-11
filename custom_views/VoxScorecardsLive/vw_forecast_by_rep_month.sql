-- VoxScorecardsLive.vw_forecast_by_rep_month (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-07-17 22:59 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH forecast_open AS (
  SELECT
    person,
    item_name,
    LOWER(TRIM(item_name)) AS name_key,
    DATE_TRUNC(SAFE.PARSE_DATE('%Y-%m-%d', date_mm3rcye8), MONTH) AS forecast_month,
    SAFE_CAST(numeric_mm3ry8p5 AS NUMERIC) AS forecast_amount
  FROM `voxdatalake.VoxScorecardsLive.new_forecast_18415088271`
  WHERE status = 'OPEN'
    AND SAFE.PARSE_DATE('%Y-%m-%d', date_mm3rcye8) >= CURRENT_DATE()
),

sales_by_customer AS (
  SELECT
    LOWER(TRIM(name)) AS name_key,
    SUM(amount)        AS matched_sales_this_month
  FROM `voxdatalake.VoxScorecardsLive.SalesDB_YTD`
  WHERE DATE(SAFE.PARSE_DATETIME('%m/%d/%Y %I:%M %p', UPPER(date_approved)))
        BETWEEN DATE_TRUNC(CURRENT_DATE(), MONTH) AND CURRENT_DATE()
  GROUP BY name_key
),

-- total of just the customer's CURRENT-month open lines, used to split the
-- reduction proportionally when they have more than one line this month
current_month_totals AS (
  SELECT
    name_key,
    SUM(forecast_amount) AS current_month_forecast_total
  FROM forecast_open
  WHERE forecast_month = DATE_TRUNC(CURRENT_DATE(), MONTH)
  GROUP BY name_key
),

forecast_adjusted AS (
  SELECT
    fo.person,
    fo.forecast_month,
    CASE
      WHEN fo.forecast_month = DATE_TRUNC(CURRENT_DATE(), MONTH)
        THEN fo.forecast_amount
             - SAFE_DIVIDE(fo.forecast_amount, cmt.current_month_forecast_total)
               * COALESCE(s.matched_sales_this_month, 0)
      ELSE fo.forecast_amount
    END AS forecast_amount_adjusted
  FROM forecast_open fo
  LEFT JOIN current_month_totals cmt USING (name_key)
  LEFT JOIN sales_by_customer s USING (name_key)
)

SELECT
  forecast_month,
  COALESCE(person, 'Unassigned') AS sales_rep,
  SUM(forecast_amount_adjusted) AS forecast_total
FROM forecast_adjusted
GROUP BY 1, 2
ORDER BY 1, 2
