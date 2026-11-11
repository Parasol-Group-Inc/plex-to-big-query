-- VoxScorecardsLive.vw_shipping_daily_snapshot_old (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-06 14:19 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH latest_date AS (
  SELECT MAX(snapshot_date) AS max_date FROM (
    SELECT MAX(snapshot_date) AS snapshot_date FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_daily`
    UNION ALL SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_blanket_daily`
    UNION ALL SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_shipped_daily`
    UNION ALL SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.shipping_daily_ops`)
),
unshipped AS (SELECT MAX(total_unshipped_revenue) AS total_unshipped_revenue FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_daily`
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_daily`)),
blanket AS (SELECT MAX(total_blanket_revenue) AS total_blanket_revenue FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_blanket_daily`
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_blanket_daily`)),
shipped AS (SELECT MAX(total_shipped_revenue) AS total_shipped_revenue FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_shipped_daily`
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.shipping_revenue_shipped_daily`)),
ops AS (SELECT MAX(sales_orders_shipped) AS sales_orders_shipped, MAX(packages_shipped) AS packages_shipped,
    MAX(new_sales_orders_received) AS new_sales_orders_received, MAX(sales_orders_in_shipping_dept) AS sales_orders_in_shipping_dept
  FROM `voxdatalake.VoxScorecardsLive.shipping_daily_ops`
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.shipping_daily_ops`))
SELECT (SELECT max_date FROM latest_date) AS report_date, unshipped.total_unshipped_revenue, blanket.total_blanket_revenue,
  shipped.total_shipped_revenue, ops.sales_orders_shipped, ops.packages_shipped, ops.new_sales_orders_received, ops.sales_orders_in_shipping_dept
FROM unshipped, blanket, shipped, ops
