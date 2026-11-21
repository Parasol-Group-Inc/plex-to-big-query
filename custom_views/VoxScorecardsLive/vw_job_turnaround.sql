-- VoxScorecardsLive.vw_job_turnaround (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-19 18:45 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH
jobs AS (
  SELECT j.Job_Key AS job_key, j.Job_No AS job_no, j.Part_Key AS part_key,
    p.Part_No AS job_part_no, pg.Part_Group AS part_group, pt.Product_Type AS product_type,
    jt.Job_Type AS job_type, js.Job_Status AS job_status,
    TIMESTAMP_MICROS(DIV(NULLIF(j.Add_Date, 0), 1000))       AS job_created_ts,
    TIMESTAMP_MICROS(DIV(NULLIF(j.Completed_Date, 0), 1000)) AS job_completed_ts
  FROM `voxdatalake.PlexProd.raw_Part_v_Job` j
  JOIN `voxdatalake.PlexProd.raw_Part_v_Part` p USING (Part_Key)
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Part_Group` pg
    ON SAFE_CAST(pg.Part_Group_Key AS INT64) = SAFE_CAST(p.Part_Group_Key AS INT64)
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Part_Product_Type` pt
    ON SAFE_CAST(pt.Product_Type_Key AS INT64) = SAFE_CAST(p.Product_Type_Key AS INT64)
  JOIN `voxdatalake.PlexProd.raw_Part_v_Job_Type` jt USING (Job_Type_Key)
  JOIN `voxdatalake.PlexProd.raw_Part_v_Job_Status` js USING (Job_Status_Key)
  WHERE js.Job_Status != 'Cancelled'
),
job_wc AS (
  SELECT SAFE_CAST(jo.Job_Key AS INT64) AS job_key,
    COALESCE(
      ARRAY_AGG(wc.Workcenter_Group IGNORE NULLS ORDER BY SAFE_CAST(jo.Op_No AS INT64) LIMIT 1)[SAFE_OFFSET(0)],
      ARRAY_AGG(o.Operation_Code IGNORE NULLS ORDER BY SAFE_CAST(jo.Op_No AS INT64) LIMIT 1)[SAFE_OFFSET(0)]
    ) AS workcenter_group
  FROM `voxdatalake.PlexProd.raw_Part_v_Job_Op` jo
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Workcenter` wc
    ON wc.Workcenter_Key = SAFE_CAST(jo.Workcenter_Key AS INT64)
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Operation` o
    ON SAFE_CAST(o.Operation_Key AS INT64) = SAFE_CAST(jo.Operation_Key AS INT64)
  GROUP BY 1
),
fg_link AS (
  SELECT Job_Key AS fg_job_key, Release_Key AS release_key
  FROM `voxdatalake.PlexProd.raw_Sales_v_Release_Job`
),
bom AS (
  SELECT DISTINCT SAFE_CAST(Part_Key AS INT64) AS parent_key, SAFE_CAST(Component_Part_Key AS INT64) AS child_key
  FROM `voxdatalake.PlexProd.raw_Part_v_BOM`
),
set_link AS (
  SELECT c.job_key, f.release_key, f.fg_job_key
  FROM fg_link f
  JOIN jobs n ON n.job_key = f.fg_job_key
  JOIN bom b ON b.parent_key = n.part_key
  JOIN jobs c ON c.part_key = b.child_key
   AND REGEXP_CONTAINS(c.job_part_no, r'^[57]')
   AND ABS(TIMESTAMP_DIFF(c.job_created_ts, n.job_created_ts, MINUTE)) <= 10
),
job_release AS (
  SELECT fg_job_key AS job_key, release_key, fg_job_key FROM fg_link
  UNION DISTINCT
  SELECT job_key, release_key, fg_job_key FROM set_link
),
fg_set AS (
  SELECT n.job_key AS set_key, n.job_key AS member_key FROM jobs n WHERE STARTS_WITH(n.job_part_no, '9')
  UNION DISTINCT
  SELECT n.job_key, c.job_key
  FROM jobs n
  JOIN bom b ON b.parent_key = n.part_key
  JOIN jobs c ON c.part_key = b.child_key
   AND REGEXP_CONTAINS(c.job_part_no, r'^[57]')
   AND ABS(TIMESTAMP_DIFF(c.job_created_ts, n.job_created_ts, MINUTE)) <= 10
  WHERE STARTS_WITH(n.job_part_no, '9')
),
set_start AS (
  SELECT s.set_key AS job_key, MIN(m.job_created_ts) AS set_start_ts, COUNT(*) AS set_job_count
  FROM fg_set s JOIN jobs m ON m.job_key = s.member_key
  GROUP BY 1
),
pending_fulfillment AS (
  SELECT SAFE_CAST(PO_Key AS INT64) AS po_key,
    MIN(TIMESTAMP_MICROS(DIV(NULLIF(Change_Date, 0), 1000))) AS pending_fulfillment_ts
  FROM `voxdatalake.PlexProd.raw_Sales_v_PO_Change`
  WHERE SAFE_CAST(PO_Status_Key AS INT64) = 2073
  GROUP BY 1
),
shipped AS (
  SELECT sl.Release_Key AS release_key,
    MIN(TIMESTAMP_MICROS(DIV(NULLIF(sh.Ship_Date, 0), 1000))) AS first_ship_ts,
    MAX(TIMESTAMP_MICROS(DIV(NULLIF(sh.Ship_Date, 0), 1000))) AS last_ship_ts,
    SUM(SAFE_CAST(sl.Quantity AS FLOAT64)) AS qty_shipped
  FROM `voxdatalake.PlexProd.raw_Sales_v_Shipper_Line` sl
  JOIN `voxdatalake.PlexProd.raw_Sales_v_Shipper` sh
    ON SAFE_CAST(sh.Shipper_Key AS INT64) = SAFE_CAST(sl.Shipper_Key AS INT64)
  JOIN `voxdatalake.PlexProd.raw_Sales_v_Shipper_Status` ss
    ON SAFE_CAST(ss.Shipper_Status_Key AS INT64) = SAFE_CAST(sh.Shipper_Status_Key AS INT64)
  WHERE ss.Shipper_Status = 'Shipped'
  GROUP BY 1
),
order_line AS (
  SELECT r.Release_Key AS release_key, SAFE_CAST(po.PO_Key AS INT64) AS po_key,
    CAST(po.Order_No AS STRING) AS order_no, pl.Line_No AS line_no, c.Name AS customer,
    fgp.Part_No AS fg_part_no, fgpt.Product_Type AS fg_product_type,
    rs.Release_Status AS line_status,
    SAFE_CAST(r.Quantity AS FLOAT64) AS qty_ordered,
    SAFE_CAST(CAST(r.Fully_Shipped AS STRING) AS BOOL) AS fully_shipped_flag,
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(po.PO_Date, 0), 1000))) AS order_date,
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.Add_Date AS STRING) AS INT64), 0), 1000)), 'America/Denver') AS order_entered_date,
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(r.Due_Date, 0), 1000))) AS due_date,
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(r.Customer_Due_Date, 0), 1000))) AS customer_due_date
  FROM `voxdatalake.PlexProd.raw_Sales_v_Release` r
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO_Line` pl
    ON SAFE_CAST(pl.PO_Line_Key AS INT64) = SAFE_CAST(r.PO_Line_Key AS INT64)
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO` po
    ON SAFE_CAST(po.PO_Key AS INT64) = SAFE_CAST(pl.PO_Key AS INT64)
  LEFT JOIN `voxdatalake.PlexProd.raw_Common_v_Customer` c ON c.Customer_No = po.Customer_No
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Part` fgp ON fgp.Part_Key = SAFE_CAST(pl.Part_Key AS INT64)
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Part_Product_Type` fgpt
    ON SAFE_CAST(fgpt.Product_Type_Key AS INT64) = SAFE_CAST(fgp.Product_Type_Key AS INT64)
  LEFT JOIN `voxdatalake.PlexProd.raw_Sales_v_Release_Status` rs
    ON SAFE_CAST(rs.Release_Status_Key AS INT64) = SAFE_CAST(r.Release_Status_Key AS INT64)
),
base AS (
  SELECT
    j.job_no, j.job_part_no, j.part_group, j.product_type, w.workcenter_group,
    j.job_type, j.job_status,
    (j.job_key = jr.fg_job_key) AS is_fg_job,
    fj.job_no AS fg_job_no,
    DATE(j.job_created_ts, 'America/Denver')   AS job_created_date,
    DATE(j.job_completed_ts, 'America/Denver') AS job_completed_date,
    STARTS_WITH(j.job_part_no, '9') AS is_fg_set_job,
    DATE(st.set_start_ts, 'America/Denver') AS set_first_job_created_date,
    st.set_job_count,
    ol.order_no, ol.line_no, ol.customer, ol.fg_part_no, ol.fg_product_type, ol.line_status,
    ol.qty_ordered, s.qty_shipped,
    (ol.line_status = 'Closed' OR ol.fully_shipped_flag) AS line_fully_shipped,
    ol.order_date, ol.order_entered_date,
    DATE(pf.pending_fulfillment_ts, 'America/Denver') AS pending_fulfillment_date,
    ol.due_date, ol.customer_due_date,
    DATE(s.first_ship_ts, 'America/Denver') AS first_ship_date,
    DATE(s.last_ship_ts, 'America/Denver')  AS last_ship_date,
    (ol.order_entered_date < DATE '2026-10-19') AS pre_golive_order
  FROM jobs j
  LEFT JOIN job_wc w USING (job_key)
  LEFT JOIN job_release jr USING (job_key)
  LEFT JOIN jobs fj ON fj.job_key = jr.fg_job_key
  LEFT JOIN set_start st ON st.job_key = j.job_key
  LEFT JOIN order_line ol ON ol.release_key = jr.release_key
  LEFT JOIN pending_fulfillment pf ON pf.po_key = ol.po_key
  LEFT JOIN shipped s ON s.release_key = jr.release_key
),
flags AS (
  SELECT b.*,
    ROW_NUMBER() OVER (PARTITION BY b.job_no ORDER BY b.due_date NULLS LAST, b.order_no, b.line_no) = 1 AS is_primary_job_row,
    -- a job tied to any pre-go-live order is treated as pre-go-live on every row
    LOGICAL_OR(COALESCE(b.pre_golive_order, FALSE)) OVER (PARTITION BY b.job_no) AS job_pre_golive,
    (b.job_created_date IS NOT NULL AND b.job_completed_date IS NOT NULL) AS job_done,
    (b.is_fg_set_job AND b.set_first_job_created_date IS NOT NULL AND b.job_completed_date IS NOT NULL) AS set_done,
    (COALESCE(b.line_fully_shipped, FALSE) AND b.pending_fulfillment_date IS NOT NULL
       AND b.last_ship_date IS NOT NULL) AS line_done
  FROM base b
),
calc AS (
  SELECT
    f.* EXCEPT (job_done, set_done, line_done, job_pre_golive),
    IF(f.job_done,
       (SELECT COUNTIF(EXTRACT(DAYOFWEEK FROM d) BETWEEN 2 AND 6)
          FROM UNNEST(GENERATE_DATE_ARRAY(DATE_ADD(f.job_created_date, INTERVAL 1 DAY), f.job_completed_date)) d),
       NULL) AS job_tat_work_days,
    IF(f.set_done,
       (SELECT COUNTIF(EXTRACT(DAYOFWEEK FROM d) BETWEEN 2 AND 6)
          FROM UNNEST(GENERATE_DATE_ARRAY(DATE_ADD(f.set_first_job_created_date, INTERVAL 1 DAY), f.job_completed_date)) d),
       NULL) AS fg_set_tat_work_days,
    IF(f.line_done,
       (SELECT COUNTIF(EXTRACT(DAYOFWEEK FROM d) BETWEEN 2 AND 6)
          FROM UNNEST(GENERATE_DATE_ARRAY(DATE_ADD(f.pending_fulfillment_date, INTERVAL 1 DAY), f.last_ship_date)) d),
       NULL) AS order_tat_work_days,
    IF(f.line_done, f.last_ship_date <= f.due_date, NULL) AS shipped_by_due_date,
    IF(f.line_done AND f.due_date IS NOT NULL,
       IF(f.last_ship_date <= f.due_date,
          (SELECT COUNTIF(EXTRACT(DAYOFWEEK FROM d) BETWEEN 2 AND 6)
             FROM UNNEST(GENERATE_DATE_ARRAY(DATE_ADD(f.last_ship_date, INTERVAL 1 DAY), f.due_date)) d),
          -(SELECT COUNTIF(EXTRACT(DAYOFWEEK FROM d) BETWEEN 2 AND 6)
             FROM UNNEST(GENERATE_DATE_ARRAY(DATE_ADD(f.due_date, INTERVAL 1 DAY), f.last_ship_date)) d)),
       NULL) AS due_vs_ship_work_days,
    (f.is_primary_job_row AND f.job_done AND NOT f.job_pre_golive) AS job_tat_valid,
    (f.is_primary_job_row AND f.set_done AND NOT f.job_pre_golive) AS fg_set_tat_valid,
    (COALESCE(f.is_fg_job, FALSE) AND f.line_done AND NOT COALESCE(f.pre_golive_order, FALSE)) AS order_tat_valid
  FROM flags f
),
std AS (
  SELECT c.product_type, c.set_month,
    ARRAY_AGG(STRUCT(s.bonus_standard_days, s.performance_standard_days)
              ORDER BY s.effective_month DESC LIMIT 1)[OFFSET(0)] AS g
  FROM (SELECT DISTINCT product_type, DATE_TRUNC(set_first_job_created_date, MONTH) AS set_month
        FROM calc WHERE is_fg_set_job AND product_type IS NOT NULL AND set_first_job_created_date IS NOT NULL) c
  JOIN `voxdatalake.VoxScorecardsLive.order_tat_standards` s
    ON s.product_type = c.product_type AND s.effective_month <= c.set_month
  GROUP BY 1, 2
)
SELECT c.*,
  CASE WHEN c.shipped_by_due_date THEN 'Y' WHEN NOT c.shipped_by_due_date THEN 'N' END AS hit_due_date,
  s.g.bonus_standard_days,
  s.g.performance_standard_days,
  CASE WHEN c.fg_set_tat_work_days IS NULL OR s.g.bonus_standard_days IS NULL THEN NULL
       WHEN c.fg_set_tat_work_days <= s.g.bonus_standard_days THEN 'Y' ELSE 'N' END AS met_bonus_standard,
  CASE WHEN c.fg_set_tat_work_days IS NULL OR s.g.performance_standard_days IS NULL THEN NULL
       WHEN c.fg_set_tat_work_days <= s.g.performance_standard_days THEN 'Y' ELSE 'N' END AS met_performance_standard
FROM calc c
LEFT JOIN std s
  ON c.is_fg_set_job
 AND s.product_type = c.product_type
 AND s.set_month = DATE_TRUNC(c.set_first_job_created_date, MONTH)
