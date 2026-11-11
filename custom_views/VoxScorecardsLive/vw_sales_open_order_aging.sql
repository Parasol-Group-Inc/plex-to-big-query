-- VoxScorecardsLive.vw_sales_open_order_aging (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 17:09 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  a.order_no, a.document_so, a.customer_name,
  ANY_VALUE(a.sales_rep_1) AS sales_rep,
  ANY_VALUE(a.status) AS status,
  MIN(a.date_created) AS date_created,
  MAX(a.days_old) AS days_old,
  CASE WHEN MAX(a.days_old) >= 90 THEN '90+ days'
       WHEN MAX(a.days_old) >= 60 THEN '60-89 days'
       WHEN MAX(a.days_old) >= 30 THEN '30-59 days'
       ELSE '14-29 days' END AS age_bucket,
  ANY_VALUE(h.next_due_date) AS next_due_date,
  SUM(a.price_total) AS order_value
FROM `voxdatalake.PlexProd.sales_orders_aging_report` a
LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_sales_line_status` ls
  ON ls.order_no = a.order_no AND ls.part_no = REGEXP_REPLACE(a.part_number, r'-Rev .*$', '')
LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_plex_order_header` h ON h.order_no = a.order_no
WHERE NOT IFNULL(ls.all_done, FALSE)
GROUP BY a.order_no, a.document_so, a.customer_name
