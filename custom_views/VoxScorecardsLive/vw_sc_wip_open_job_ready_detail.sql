-- VoxScorecardsLive.vw_sc_wip_open_job_ready_detail (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-12 15:54 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH l AS (
  SELECT *,
    IF(IFNULL(release_status, '') != 'Blanket', ready_value, 0) AS ready_bucket_value,
    IF(remaining_sort IN (2, 3), remaining_value, 0) AS open_job_value
  FROM `voxdatalake.VoxScorecardsLive.vw_sc_wip_status_lines`
),
l2 AS (SELECT * FROM l WHERE ready_bucket_value > 0 OR open_job_value != 0),
rj AS (SELECT DISTINCT SAFE_CAST(Release_Key AS INT64) release_key, SAFE_CAST(Job_Key AS INT64) job_key FROM `voxdatalake.PlexProd.raw_Sales_v_Release_Job`),
wc AS (
  SELECT SAFE_CAST(SAFE_CAST(CAST(Workcenter_Key AS STRING) AS FLOAT64) AS INT64) AS wk, Name, Workcenter_Code
  FROM `voxdatalake.PlexProd.raw_Part_v_Workcenter`
),
ops AS (
  SELECT SAFE_CAST(o.Job_Key AS INT64) job_key, SAFE_CAST(o.Job_Op_Key AS INT64) job_op_key, SAFE_CAST(o.Op_No AS INT64) op_no,
    o.Complete_Date IS NOT NULL AS op_done, o.Start_Date IS NOT NULL AS op_started,
    op.Operation_Code AS operation,
    COALESCE(w.Name, w.Workcenter_Code) AS workcenter
  FROM `voxdatalake.PlexProd.raw_Part_v_Job_Op` o
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Operation` op ON SAFE_CAST(op.Operation_Key AS INT64) = SAFE_CAST(o.Operation_Key AS INT64)
  LEFT JOIN wc w ON w.wk = SAFE_CAST(SAFE_CAST(CAST(o.Workcenter_Key AS STRING) AS FLOAT64) AS INT64)
  WHERE SAFE_CAST(o.Job_Key AS INT64) IN (SELECT job_key FROM rj)
),
prod AS (SELECT SAFE_CAST(Job_Op_Key AS INT64) job_op_key, SUM(SAFE_CAST(Quantity AS FLOAT64)) qty FROM `voxdatalake.PlexProd.raw_Part_v_Production` GROUP BY 1),
op_roll AS (
  SELECT job_key, COUNTIF(op_done) ops_done, COUNT(*) ops_total, MAX(op_no) last_op_no,
    ARRAY_AGG(IF(op_done, NULL, STRUCT(op_no, operation, workcenter, op_started)) IGNORE NULLS ORDER BY op_no LIMIT 1)[SAFE_OFFSET(0)] cur
  FROM ops GROUP BY job_key
),
last_prod AS (
  SELECT o.job_key, SUM(IFNULL(p.qty, 0)) qty_produced
  FROM ops o JOIN op_roll r ON r.job_key = o.job_key AND o.op_no = r.last_op_no
  LEFT JOIN prod p ON p.job_op_key = o.job_op_key GROUP BY 1
),
job AS (
  SELECT SAFE_CAST(j.Job_Key AS INT64) job_key, j.Job_No AS job_no, js.Job_Status AS job_status,
    SAFE_CAST(j.Quantity AS FLOAT64) AS job_qty,
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(j.Due_Date AS STRING) AS INT64), 0), 1000)), 'America/Denver') AS job_due_date,
    COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0 AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
      AND COALESCE(SAFE_CAST(js.Scrapped_Status AS INT64), 0) = 0 AS is_open
  FROM `voxdatalake.PlexProd.raw_Part_v_Job` j
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Job_Status` js ON SAFE_CAST(js.Job_Status_Key AS INT64) = SAFE_CAST(j.Job_Status_Key AS INT64)
  WHERE SAFE_CAST(j.Job_Key AS INT64) IN (SELECT job_key FROM rj)
),
per_line AS (
  SELECT rj.release_key,
    STRING_AGG(jb.job_no, ', ' ORDER BY jb.job_no) AS job_nos,
    STRING_AGG(jb.job_no || ': ' || IFNULL(jb.job_status, '?'), '; ' ORDER BY jb.job_no) AS job_statuses,
    SUM(IF(jb.is_open, jb.job_qty, 0)) AS open_job_qty,
    MIN(IF(jb.is_open, jb.job_due_date, NULL)) AS job_due_date,
    STRING_AGG(DISTINCT IF(jb.is_open, IFNULL(r.cur.operation, 'Job open, no open operation'), NULL), '; '
               ORDER BY IF(jb.is_open, IFNULL(r.cur.operation, 'Job open, no open operation'), NULL)) AS current_operation,
    STRING_AGG(DISTINCT IF(jb.is_open, r.cur.workcenter, NULL), '; ' ORDER BY IF(jb.is_open, r.cur.workcenter, NULL)) AS assigned_workcenter,
    STRING_AGG(IF(jb.is_open, CAST(IFNULL(r.ops_done, 0) AS STRING) || ' of ' || CAST(IFNULL(r.ops_total, 0) AS STRING), NULL), '; ' ORDER BY jb.job_no) AS ops_done,
    LOGICAL_OR(jb.is_open AND IFNULL(r.cur.op_started, FALSE)) AS current_op_started,
    SUM(IF(jb.is_open, IFNULL(lp.qty_produced, 0), 0)) AS qty_produced
  FROM rj JOIN job jb USING (job_key)
  LEFT JOIN op_roll r USING (job_key)
  LEFT JOIN last_prod lp USING (job_key)
  GROUP BY 1
)
SELECT
  CASE WHEN l2.ready_bucket_value > 0 AND l2.open_job_value != 0 THEN 'Ready to ship + Open job (partly made)'
       WHEN l2.ready_bucket_value > 0 THEN 'Ready to ship (already made)'
       ELSE 'Open job' END AS bucket,
  l2.order_no, l2.document_so, l2.customer_name, l2.sales_rep, l2.release_status AS line_status, l2.is_on_hold,
  l2.next_due_date AS order_due_date,
  l2.part_no, l2.part_name, l2.qty_pending, l2.ready_qty,
  GREATEST(l2.qty_pending - l2.ready_qty, 0) AS qty_to_make,
  l2.price_ea,
  l2.ready_bucket_value AS ready_value, l2.open_job_value, l2.ready_bucket_value + l2.open_job_value AS line_value,
  pl.job_nos, pl.job_statuses, pl.open_job_qty, pl.job_due_date,
  CASE WHEN l2.open_job_value = 0 THEN pl.current_operation
       WHEN l2.remaining_sort = 3 THEN 'Job done, short'
       ELSE pl.current_operation END AS current_operation,
  pl.assigned_workcenter, pl.ops_done, pl.current_op_started, pl.qty_produced,
  CASE
    WHEN l2.remaining_sort = 3 AND l2.open_job_value != 0 AND l2.ready_qty > 0
      THEN 'Job completed but ' || FORMAT('%\'d', CAST(ROUND(l2.qty_pending - l2.ready_qty) AS INT64)) || ' short; no open job for the rest'
    WHEN l2.remaining_sort = 3 AND l2.open_job_value != 0
      THEN 'Job completed, nothing in finished stock for this line; no open job'
  END AS note
FROM l2 LEFT JOIN per_line pl USING (release_key)
