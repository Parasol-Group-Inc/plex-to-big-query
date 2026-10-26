-- bottling_job_open_with_orders_report — open Bottling jobs with the sales order(s) behind them
--
-- Origin: hand-made in BigQuery by Jennilyn on 2026-10-26 as a workaround, brought under
-- version control the same day. Plex's Job_Distribution view returns 0 rows (prod and test),
-- so jobs are tied to orders another way (question open with the Plex champion; OPEN_ITEMS).
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime. Do NOT hardcode them.
--
-- GRAIN: one row per open Bottling job.
-- order_no / order_source:
--   Direct    = job created from a sales order release (Sales_v_Release_Job)
--   Suggested = no direct link; Pending Fulfillment orders for the finished parts whose BOM
--               uses this job's part (fg_parts_using_this_part shows which)
--   Stock jobs show 'Stock Job'; other job types show 'N/A - <type>'.
--
-- CROSS-PIPELINE DEPENDENCY: reads {dataset}.sales_orders_report (sales_orders pipeline)
-- and raw_Sales_v_* tables written by that pipeline. If it is ever created before those exist,
-- the retry-once pass in main() does not help across pipelines; re-run work_orders.

WITH open_bottling_jobs AS (
  SELECT DISTINCT
    SAFE_CAST(j.Job_Key AS INT64)    AS job_key,
    SAFE_CAST(j.Part_Key AS INT64)   AS part_key,
    j.Job_No                         AS job_no,
    p.Part_No                        AS part_no,
    p.Name                           AS part_name,
    jt.Job_Type                      AS job_type,
    js.Job_Status                    AS job_status,
    SAFE_CAST(j.Quantity AS FLOAT64) AS qty_pending,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(j.Add_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(j.Add_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(j.Add_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                AS date_entered
  FROM `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
    ON SAFE_CAST(jo.Job_Key AS INT64) = SAFE_CAST(j.Job_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
    ON SAFE_CAST(jo.Workcenter_Key AS INT64) = wc.Workcenter_Key
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
    ON SAFE_CAST(j.Part_Key AS INT64) = p.Part_Key
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Status` js
    ON SAFE_CAST(j.Job_Status_Key AS INT64) = SAFE_CAST(js.Job_Status_Key AS INT64)
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Type` jt
    ON SAFE_CAST(j.Job_Type_Key AS INT64) = SAFE_CAST(jt.Job_Type_Key AS INT64)
  WHERE wc.Workcenter_Group = 'Bottling'
    AND COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(js.Hold_Status AS INT64), 0) = 0
),

-- Job created directly from a sales order release
direct_lines AS (
  SELECT DISTINCT
    SAFE_CAST(rj.Job_Key AS INT64) AS job_key,
    CAST(po.Order_No AS STRING)    AS order_no,
    c.Name                         AS customer
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Release_Job` rj
  JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
    ON SAFE_CAST(rel.Release_Key AS INT64) = SAFE_CAST(rj.Release_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pl
    ON SAFE_CAST(pl.PO_Line_Key AS INT64) = SAFE_CAST(rel.PO_Line_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO` po
    ON SAFE_CAST(po.PO_Key AS INT64) = SAFE_CAST(pl.PO_Key AS INT64)
  LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` c
    ON c.Customer_No = po.Customer_No
),

-- No direct link: Pending Fulfillment orders for the 9s whose BOM uses this part
suggested_lines AS (
  SELECT DISTINCT
    obj.job_key,
    CAST(so.order_no AS STRING) AS order_no,
    so.customer_name            AS customer,
    so.part_number              AS fg_part
  FROM open_bottling_jobs obj
  JOIN `{gcp_project}.{dataset}.raw_Part_v_BOM` b
    ON SAFE_CAST(b.Component_Part_Key AS INT64) = obj.part_key
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p9
    ON p9.Part_Key = SAFE_CAST(b.Part_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.sales_orders_report` so
    ON so.part_number = p9.Part_No
   AND so.status = 'Pending Fulfillment'
),

direct_agg AS (
  SELECT
    job_key,
    STRING_AGG(order_no, ', ' ORDER BY SAFE_CAST(order_no AS INT64)) AS order_no,
    STRING_AGG(DISTINCT customer, ', ')                             AS customer
  FROM (SELECT DISTINCT job_key, order_no, customer FROM direct_lines)
  GROUP BY job_key
),
suggested_orders AS (
  SELECT
    job_key,
    STRING_AGG(order_no, ', ' ORDER BY SAFE_CAST(order_no AS INT64)) AS order_no
  FROM (SELECT DISTINCT job_key, order_no FROM suggested_lines)
  GROUP BY job_key
),
suggested_info AS (
  SELECT
    job_key,
    STRING_AGG(DISTINCT customer, ', ') AS customer,
    STRING_AGG(DISTINCT fg_part, ', ')  AS fg_parts
  FROM suggested_lines
  GROUP BY job_key
)

SELECT
  obj.job_no,
  obj.part_no,
  obj.part_name,
  obj.job_type,
  obj.job_status,
  obj.qty_pending,
  obj.date_entered,
  CASE
    WHEN obj.job_type = 'Stock'       THEN 'Stock Job'
    WHEN obj.job_type = 'Sales Order' THEN COALESCE(d.order_no, so.order_no, 'No open order found')
    ELSE CONCAT('N/A - ', IFNULL(obj.job_type, 'No job type'))
  END AS order_no,
  CASE
    WHEN obj.job_type <> 'Sales Order' THEN NULL
    WHEN d.order_no  IS NOT NULL       THEN 'Direct'
    WHEN so.order_no IS NOT NULL       THEN 'Suggested'
  END AS order_source,
  CASE
    WHEN obj.job_type = 'Stock' THEN 'Warehouse'
    ELSE COALESCE(d.customer, si.customer)
  END AS customer,
  IF(obj.job_type = 'Sales Order' AND d.order_no IS NULL, si.fg_parts, NULL) AS fg_parts_using_this_part
FROM open_bottling_jobs obj
LEFT JOIN direct_agg d        ON d.job_key  = obj.job_key
LEFT JOIN suggested_orders so ON so.job_key = obj.job_key
LEFT JOIN suggested_info si   ON si.job_key = obj.job_key
