-- VoxScorecardsLive.vw_sales_orders_over_10k (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 17:09 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH canc AS (SELECT order_no, SUM(canceled_value) AS canceled_value FROM `voxdatalake.VoxScorecardsLive.vw_sales_line_status` GROUP BY 1),
t AS (
  SELECT t.order_no, t.document_so, t.customer_name, h.sales_rep, t.status, t.date_created, h.next_due_date,
    t.order_total_computed - IFNULL(c.canceled_value, 0) AS order_value,
    IFNULL(c.canceled_value, 0) AS canceled_value_removed
  FROM `voxdatalake.PlexProd.sales_orders_over_10k_report` t
  LEFT JOIN canc c USING (order_no)
  LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_plex_order_header` h USING (order_no)
  WHERE t.status_key NOT IN (2074, 2076)
)
SELECT *, RANK() OVER (ORDER BY order_value DESC) AS value_rank
FROM t WHERE order_value >= 10000
