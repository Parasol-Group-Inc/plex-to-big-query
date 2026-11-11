-- VoxScorecardsLive.vw_sales_top_wip_orders (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 17:09 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT order_no, ANY_VALUE(document_so) AS document_so, ANY_VALUE(customer_name) AS customer_name,
  ANY_VALUE(sales_rep) AS sales_rep, ANY_VALUE(next_due_date) AS next_due_date,
  SUM(wip_value) AS wip_value,
  RANK() OVER (ORDER BY SUM(wip_value) DESC) AS value_rank
FROM `voxdatalake.VoxScorecardsLive.vw_sc_wip_status_lines`
GROUP BY order_no
