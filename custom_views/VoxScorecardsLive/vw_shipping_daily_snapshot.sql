-- VoxScorecardsLive.vw_shipping_daily_snapshot (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-17 14:20 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH params AS (
  SELECT CASE EXTRACT(DAYOFWEEK FROM CURRENT_DATE('America/Denver'))
           WHEN 2 THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 3 DAY)
           WHEN 1 THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 2 DAY)
           ELSE DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY)
         END AS report_date
),
p AS (SELECT report_date, DATE_TRUNC(report_date, WEEK(MONDAY)) AS week_start FROM params),
ship AS (
  SELECT s.ship_date, s.order_no, s.shipper_no, s.shipping_revenue, s.quantity_shipped
  FROM `voxdatalake.PlexProd.shipping_revenue_report` s, p
  WHERE s.ship_date BETWEEN p.week_start AND p.report_date
),
adj AS (
  SELECT a.ship_date, a.amount FROM `voxdatalake.VoxScorecardsLive.vw_sc_revenue_adjustments` a, p
  WHERE a.ship_date BETWEEN p.week_start AND p.report_date
),
shipped_shippers AS (
  SELECT SAFE_CAST(s.Shipper_Key AS INT64) AS shipper_key,
    COALESCE(DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS INT64), 0), 1000))),
             NULLIF(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS DATE), DATE '1970-01-01'),
             NULLIF(DATE(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')) AS ship_date
  FROM `voxdatalake.PlexProd.raw_Sales_v_Shipper` s
  JOIN `voxdatalake.PlexProd.raw_Sales_v_Shipper_Status` ss
    ON SAFE_CAST(ss.Shipper_Status_Key AS INT64) = SAFE_CAST(s.Shipper_Status_Key AS INT64)
  WHERE SAFE_CAST(ss.Shipped AS INT64) = 1
),
cont AS (
  SELECT sh.ship_date, COUNT(DISTINCT sc.Serial_No) AS n_containers
  FROM shipped_shippers sh
  JOIN `voxdatalake.PlexProd.raw_Sales_v_Shipper_Line` sl ON SAFE_CAST(sl.Shipper_Key AS INT64) = sh.shipper_key
  JOIN `voxdatalake.PlexProd.raw_Sales_v_Shipper_Container` sc ON SAFE_CAST(sc.Shipper_Line_Key AS INT64) = SAFE_CAST(sl.Shipper_Line_Key AS INT64)
  CROSS JOIN p
  WHERE sh.ship_date BETWEEN p.week_start AND p.report_date
  GROUP BY 1
),
unshipped AS (
  SELECT MAX(total_unshipped_revenue) AS total_unshipped_revenue, MAX(snapshot_date) AS unshipped_as_of
  FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_daily`
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_daily`)
),
blanket AS (
  SELECT MAX(total_blanket_revenue) AS total_blanket_revenue
  FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_blanket_daily`
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_blanket_daily`)
),
ops AS (
  SELECT MAX(packages_shipped) AS packages_shipped_upload,
         MAX(new_sales_orders_received) AS new_sales_orders_received,
         MAX(sales_orders_in_shipping_dept) AS sales_orders_in_shipping_dept
  FROM `voxdatalake.VoxScorecardsLive.shipping_daily_ops`, p
  WHERE snapshot_date = p.report_date
)
SELECT
  p.report_date,
  p.week_start,
  (SELECT COALESCE(SUM(shipping_revenue), 0) FROM ship WHERE ship_date = p.report_date)
    + (SELECT COALESCE(SUM(amount), 0) FROM adj WHERE ship_date = p.report_date)        AS total_shipped_revenue,
  (SELECT COALESCE(SUM(shipping_revenue), 0) FROM ship)
    + (SELECT COALESCE(SUM(amount), 0) FROM adj)                                        AS shipped_revenue_wtd,
  (SELECT COUNT(DISTINCT order_no) FROM ship WHERE ship_date = p.report_date)           AS sales_orders_shipped,
  (SELECT COUNT(DISTINCT order_no) FROM ship)                                           AS sales_orders_shipped_wtd,
  (SELECT COUNT(DISTINCT shipper_no) FROM ship WHERE ship_date = p.report_date)         AS shippers_yesterday,
  (SELECT COALESCE(SUM(quantity_shipped), 0) FROM ship WHERE ship_date = p.report_date) AS units_shipped_yesterday,
  (SELECT COALESCE(SUM(n_containers), 0) FROM cont WHERE ship_date = p.report_date)     AS packages_shipped,
  (SELECT COALESCE(SUM(n_containers), 0) FROM cont)                                     AS packages_shipped_wtd,
  ops.packages_shipped_upload,
  ops.new_sales_orders_received,
  ops.sales_orders_in_shipping_dept,
  unshipped.total_unshipped_revenue,
  unshipped.unshipped_as_of,
  blanket.total_blanket_revenue
FROM p CROSS JOIN unshipped CROSS JOIN blanket LEFT JOIN ops ON TRUE
