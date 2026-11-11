-- VoxScorecardsLive.vw_sc_wip_status_summary (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 15:52 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH u AS (
  SELECT 1 AS sort_order, 'Ready to ship (already made)' AS status, order_no, ready_value AS value
  FROM `voxdatalake.VoxScorecardsLive.vw_sc_wip_status_lines` WHERE ready_value > 0
  UNION ALL
  SELECT IF(remaining_sort = 3, 2, remaining_sort),
         IF(remaining_sort = 3, 'Open job', remaining_status),
         order_no, remaining_value
  FROM `voxdatalake.VoxScorecardsLive.vw_sc_wip_status_lines` WHERE remaining_value != 0
)
SELECT sort_order, status, COUNT(*) AS lines, COUNT(DISTINCT order_no) AS orders, SUM(value) AS value,
  SAFE_DIVIDE(SUM(value), SUM(SUM(value)) OVER ()) AS pct_of_wip
FROM u GROUP BY 1, 2
