-- VoxScorecardsLive.vw_sales_rush_orders (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 17:09 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  r.order_no, r.document_so, r.customer_name,
  ANY_VALUE(r.sales_rep_1) AS sales_rep,
  ANY_VALUE(r.status) AS status,
  ANY_VALUE(r.memo) AS memo,
  MIN(r.date_created) AS date_created,
  ANY_VALUE(h.next_due_date) AS next_due_date,
  SUM(r.price_total) AS order_value,
  RANK() OVER (ORDER BY SUM(r.price_total) DESC) AS value_rank
FROM `voxdatalake.PlexProd.sales_orders_rush_open_report` r
LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_sales_line_status` ls
  ON ls.order_no = r.order_no AND ls.part_no = REGEXP_REPLACE(r.part_number, r'-Rev .*$', '')
LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_plex_order_header` h ON h.order_no = r.order_no
WHERE NOT IFNULL(ls.all_done, FALSE)
GROUP BY r.order_no, r.document_so, r.customer_name
