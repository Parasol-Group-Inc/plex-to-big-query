-- VoxScorecardsLive.vw_forecast_decrementing (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-07-17 22:44 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH forecast_open AS (
  SELECT
    f.*,
    LOWER(TRIM(f.item_name)) AS name_key,
    SAFE_CAST(f.numeric_mm3ry8p5 AS FLOAT64) AS numeric_mm3ry8p5_num
  FROM `voxdatalake.VoxScorecardsLive.new_forecast_18415088271` f
  WHERE f.status = 'OPEN'
    AND SAFE.PARSE_DATE('%Y-%m-%d', f.date_mm3rcye8) >= CURRENT_DATE()
),

customer_forecast_totals AS (
  SELECT
    name_key,
    SUM(numeric_mm3ry8p5_num) AS customer_open_forecast_total
  FROM forecast_open
  GROUP BY name_key
),

sales_by_customer AS (
  SELECT
    LOWER(TRIM(name)) AS name_key,
    SUM(amount)        AS customer_matched_sales_this_month
  FROM `voxdatalake.VoxScorecardsLive.SalesDB_YTD`
  WHERE DATE(SAFE.PARSE_DATETIME('%m/%d/%Y %I:%M %p', UPPER(date_approved)))
        BETWEEN DATE_TRUNC(CURRENT_DATE(), MONTH) AND CURRENT_DATE()
  GROUP BY name_key
)

SELECT
  fo.* EXCEPT(name_key, numeric_mm3ry8p5_num),
  ct.customer_open_forecast_total,
  COALESCE(s.customer_matched_sales_this_month, 0) AS customer_matched_sales_this_month,
  fo.numeric_mm3ry8p5_num
    - SAFE_DIVIDE(fo.numeric_mm3ry8p5_num, ct.customer_open_forecast_total)
      * COALESCE(s.customer_matched_sales_this_month, 0)
    AS numeric_mm3ry8p5_adjusted
FROM forecast_open fo
JOIN customer_forecast_totals ct USING (name_key)
LEFT JOIN sales_by_customer s USING (name_key)
