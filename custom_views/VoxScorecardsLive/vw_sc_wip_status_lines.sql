-- VoxScorecardsLive.vw_sc_wip_status_lines (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 15:55 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH rstat AS (
  SELECT SAFE_CAST(r.Release_Key AS INT64) AS release_key, rs.Release_Status AS release_status,
         COALESCE(SAFE_CAST(rs.Cancelled_Status AS INT64), 0) = 1
           OR COALESCE(SAFE_CAST(rs.Shipped_Status AS INT64), 0) = 1
           OR COALESCE(SAFE_CAST(rs.Closed_Status AS INT64), 0) = 1
           OR UPPER(rs.Release_Status) IN ('CANCELED', 'CANCELLED', 'CLOSED', 'SHIPPED') AS is_done
  FROM `voxdatalake.PlexProd.raw_Sales_v_Release` r
  LEFT JOIN `voxdatalake.PlexProd.raw_Sales_v_Release_Status` rs
    ON SAFE_CAST(rs.Release_Status_Key AS INT64) = SAFE_CAST(r.Release_Status_Key AS INT64)
),
w AS (
  SELECT w.*, rs.release_status
  FROM `voxdatalake.PlexProd.sales_order_value_by_status_report` w
  LEFT JOIN rstat rs USING (release_key)
  WHERE w.is_pending_fulfillment
    AND NOT IFNULL(rs.is_done, FALSE)
    AND NOT (IFNULL(w.qty_pending, 0) <= 0 AND IFNULL(w.wip_value, 0) = 0)
),
rel AS (
  SELECT SAFE_CAST(r.Release_Key AS INT64) AS release_key, SAFE_CAST(pl.Part_Key AS INT64) AS part_key, pl.PO_Line_Key,
    SAFE_CAST(r.Quantity AS FLOAT64) - COALESCE(SAFE_CAST(r.Quantity_Shipped AS FLOAT64), 0) AS rem_qty,
    COALESCE(SAFE_CAST(CAST(r.Due_Date AS STRING) AS DATE),
             DATE(TIMESTAMP_MICROS(DIV(SAFE_CAST(CAST(r.Due_Date AS STRING) AS INT64), 1000)))) AS due_date
  FROM `voxdatalake.PlexProd.raw_Sales_v_Release` r
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO_Line` pl ON r.PO_Line_Key = pl.PO_Line_Key
  WHERE SAFE_CAST(r.Release_Key AS INT64) IN (SELECT release_key FROM w)
),
oh AS (SELECT part_key, SUM(on_hand_qty) AS on_hand FROM `voxdatalake.PlexProd.part_on_hand_inventory_report` GROUP BY 1),
alloc AS (
  SELECT rel.release_key, rel.rem_qty, COALESCE(oh.on_hand, 0) AS on_hand,
    COALESCE(SUM(rem_qty) OVER (PARTITION BY rel.part_key ORDER BY due_date, PO_Line_Key, release_key
                                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS qty_ahead
  FROM rel LEFT JOIN oh USING (part_key) WHERE rem_qty > 0
),
ready AS (SELECT release_key, LEAST(rem_qty, GREATEST(on_hand - qty_ahead, 0)) AS ready_qty FROM alloc),
jobs AS (
  SELECT SAFE_CAST(rj.Release_Key AS INT64) AS release_key,
    STRING_AGG(DISTINCT j.Job_No, ', ') AS job_nos,
    LOGICAL_OR(COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0
           AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
           AND COALESCE(SAFE_CAST(js.Scrapped_Status AS INT64), 0) = 0) AS has_open_job,
    LOGICAL_OR(SAFE_CAST(js.Completed_Status AS INT64) = 1) AS has_completed_job
  FROM `voxdatalake.PlexProd.raw_Sales_v_Release_Job` rj
  JOIN `voxdatalake.PlexProd.raw_Part_v_Job` j ON SAFE_CAST(j.Job_Key AS INT64) = SAFE_CAST(rj.Job_Key AS INT64)
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Job_Status` js ON SAFE_CAST(js.Job_Status_Key AS INT64) = SAFE_CAST(j.Job_Status_Key AS INT64)
  GROUP BY 1
),
x AS (
  SELECT w.*, h.sales_rep, h.next_due_date, j.job_nos,
    IF(REGEXP_CONTAINS(w.part_no, r'^\d'), IFNULL(rd.ready_qty, 0), 0) AS ready_qty,
    IF(REGEXP_CONTAINS(w.part_no, r'^\d'),
       GREATEST(0, LEAST(w.wip_value, IFNULL(rd.ready_qty, 0) * IFNULL(w.price_ea, 0))), 0) AS ready_value,
    CASE
      WHEN w.part_no = 'NEW PRODUCT'                THEN 6
      WHEN NOT REGEXP_CONTAINS(w.part_no, r'^\d')   THEN 7
      WHEN j.has_open_job                           THEN 2
      WHEN j.has_completed_job                      THEN 3
      WHEN w.release_status = 'Label Design'        THEN 4
      ELSE 5 END AS remaining_sort
  FROM w
  LEFT JOIN ready rd USING (release_key)
  LEFT JOIN jobs j USING (release_key)
  LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_plex_order_header` h ON h.order_no = w.order_no
)
SELECT
  order_no, document_so, so_status, release_status, is_on_hold, customer_name, sales_rep, next_due_date,
  part_no, part_name, release_key, job_nos,
  qty_pending, price_ea, wip_value,
  ready_qty, ready_value,
  wip_value - ready_value AS remaining_value,
  remaining_sort,
  CASE remaining_sort
    WHEN 2 THEN 'Open job'
    WHEN 3 THEN 'Job completed, waiting on another job'
    WHEN 4 THEN 'Label design'
    WHEN 5 THEN 'No job linked'
    WHEN 6 THEN 'New product placeholder'
    WHEN 7 THEN 'Services, fees, credits' END AS remaining_status
FROM x
