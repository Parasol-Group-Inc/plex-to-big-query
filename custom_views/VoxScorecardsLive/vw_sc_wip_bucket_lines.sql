-- VoxScorecardsLive.vw_sc_wip_bucket_lines (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-19 17:22 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH l AS (
  SELECT *, (ready_value > 0 AND remaining_value != 0) AS is_split_line
  FROM `voxdatalake.VoxScorecardsLive.vw_sc_wip_status_lines`
),
u AS (
  SELECT IF(release_status = 'Blanket', 15, 10) AS bucket_sort,
         IF(release_status = 'Blanket', 'Blankets in shipping', 'Ready to ship (already made)') AS bucket,
         l.*, ready_qty AS bucket_qty, ready_value AS bucket_value
  FROM l WHERE ready_value > 0
  UNION ALL
  SELECT CASE remaining_sort WHEN 2 THEN 20 WHEN 3 THEN 20 WHEN 4 THEN 40 WHEN 5 THEN 50 WHEN 6 THEN 60 ELSE 70 END,
         IF(remaining_sort = 3, 'Open job', remaining_status),
         l.*, GREATEST(COALESCE(qty_pending, 0) - COALESCE(ready_qty, 0), 0), remaining_value
  FROM l WHERE remaining_value != 0
)
SELECT
  bucket_sort, bucket,
  document_so, order_no, customer_name, sales_rep,
  next_due_date, is_on_hold, release_status, so_status,
  part_no, part_name, job_nos,
  bucket_qty, price_ea, bucket_value,
  qty_pending AS line_qty_pending, wip_value AS line_wip_value, is_split_line
FROM u
