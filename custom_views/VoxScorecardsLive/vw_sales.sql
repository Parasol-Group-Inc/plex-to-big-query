-- VoxScorecardsLive.vw_sales (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 15:49 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT date_approved, name, sales_rep, sales_rep_2, amount
FROM `voxdatalake.VoxScorecardsLive.sales_history_static`
UNION ALL
-- Plex: one row per order, dated the first day it reached Pending Fulfillment
SELECT
  sales_date            AS date_approved,
  customer_name         AS name,
  sales_rep,
  sales_rep_2,
  SUM(sales_value)      AS amount
FROM `voxdatalake.PlexProd.sales_mtd_by_status_change_report`
WHERE sales_date >= DATE '2026-11-01'
GROUP BY sales_date, order_no, customer_name, sales_rep, sales_rep_2
