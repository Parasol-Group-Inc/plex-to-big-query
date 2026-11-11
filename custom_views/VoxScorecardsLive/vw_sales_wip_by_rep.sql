-- VoxScorecardsLive.vw_sales_wip_by_rep (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 17:43 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  COALESCE(w.sales_rep, '(no rep)') AS sales_rep,
  IF(r.sales_rep IS NOT NULL AND r.active, 'Primary', 'Other') AS rep_type,
  r.sort_order AS rep_sort,
  COUNT(*) AS open_orders,
  SUM(w.wip_value) AS wip_value,
  COUNTIF(w.next_due_date < CURRENT_DATE('America/Denver')) AS orders_past_due,
  SUM(IF(w.next_due_date < CURRENT_DATE('America/Denver'), w.wip_value, 0)) AS wip_value_past_due
FROM `voxdatalake.VoxScorecardsLive.vw_sales_top_wip_orders` w
LEFT JOIN `voxdatalake.VoxScorecardsLive.sales_rep_roster` r ON r.sales_rep = w.sales_rep
GROUP BY 1, 2, 3
