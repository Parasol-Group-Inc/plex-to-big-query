-- VoxScorecardsLive.vw_sc_production_daily_mtd (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-17 15:12 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH params AS (
  SELECT CASE EXTRACT(DAYOFWEEK FROM CURRENT_DATE('America/Denver'))
           WHEN 2 THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 3 DAY)
           WHEN 1 THEN DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 2 DAY)
           ELSE DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY)
         END AS yday
),
wc AS (SELECT SAFE_CAST(Workcenter_Key AS INT64) AS Workcenter_Key, Workcenter_Group FROM `voxdatalake.PlexProd.raw_Part_v_Workcenter`),
part AS (
  SELECT SAFE_CAST(Part_Key AS INT64) AS Part_Key, TRIM(COALESCE(Part_No, '')) AS part_no, LOWER(TRIM(COALESCE(Unit, ''))) AS unit
  FROM `voxdatalake.PlexProd.raw_Part_v_Part`
),
prod AS (
  SELECT w.Workcenter_Group, pt.part_no,
    COALESCE(SAFE_CAST(p.Rejected AS INT64), 0) != 0 AS is_scrap,
    DATE(COALESCE(
      DATETIME(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(p.Record_Date AS STRING) AS INT64), 0), 1000))),
      SAFE_CAST(CAST(p.Record_Date AS STRING) AS DATETIME))) AS production_date,
    CASE
      WHEN w.Workcenter_Group != 'Pre-Weigh' THEN SAFE_CAST(p.Quantity AS FLOAT64)
      WHEN pt.unit IN ('gs', 'g', 'grams')  THEN SAFE_CAST(p.Quantity AS FLOAT64) / 1000
      WHEN pt.unit IN ('mg', 'mgs')         THEN SAFE_CAST(p.Quantity AS FLOAT64) / 1000000
      WHEN pt.unit IN ('lbs', 'lb')         THEN SAFE_CAST(p.Quantity AS FLOAT64) * 0.45359237
      ELSE SAFE_CAST(p.Quantity AS FLOAT64)
    END AS qty
  FROM `voxdatalake.PlexProd.raw_Part_v_Production` p
  JOIN wc w ON SAFE_CAST(p.Workcenter_Key AS INT64) = w.Workcenter_Key
  LEFT JOIN part pt ON SAFE_CAST(p.Part_Key AS INT64) = pt.Part_Key
),
yday_qty AS (
  SELECT Workcenter_Group, SUM(qty) AS qty
  FROM prod, params
  WHERE NOT is_scrap AND production_date = params.yday
    AND NOT (Workcenter_Group = 'Bottling' AND STARTS_WITH(part_no, '9') AND NOT REGEXP_CONTAINS(part_no, r'^9[0-9]{4}-BK'))
  GROUP BY 1
),
yday_blends AS (
  SELECT COUNT(DISTINCT SAFE_CAST(jo.Job_Key AS INT64)) AS jobs
  FROM `voxdatalake.PlexProd.raw_Part_v_Job_Op` jo
  JOIN wc w ON SAFE_CAST(jo.Workcenter_Key AS INT64) = w.Workcenter_Key
  CROSS JOIN params
  WHERE w.Workcenter_Group = 'Blending'
    AND COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(jo.Complete_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(jo.Complete_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(jo.Complete_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')) = params.yday
),
lab_ops AS (
  SELECT DISTINCT SAFE_CAST(o.Job_Key AS INT64) AS job_key
  FROM `voxdatalake.PlexProd.raw_Part_v_Job_Op` o
  JOIN `voxdatalake.PlexProd.raw_Part_v_Operation` op ON SAFE_CAST(op.Operation_Key AS INT64) = SAFE_CAST(o.Operation_Key AS INT64)
  WHERE op.Operation_Code = 'Labeling' AND o.Complete_Date IS NULL
),
lab_jobs AS (
  SELECT SAFE_CAST(j.Job_Key AS INT64) AS job_key, SAFE_CAST(j.Quantity AS FLOAT64) AS job_qty
  FROM `voxdatalake.PlexProd.raw_Part_v_Job` j
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Job_Status` js ON SAFE_CAST(js.Job_Status_Key AS INT64) = SAFE_CAST(j.Job_Status_Key AS INT64)
  WHERE COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0 AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(js.Hold_Status AS INT64), 0) = 0 AND COALESCE(SAFE_CAST(js.Scrapped_Status AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(js.Template_Status AS INT64), 0) = 0
),
lab_good AS (
  SELECT SAFE_CAST(o.Job_Key AS INT64) AS job_key,
         SUM(IF(COALESCE(SAFE_CAST(p.Rejected AS INT64), 0) = 0, SAFE_CAST(p.Quantity AS FLOAT64), 0)) AS good_qty
  FROM `voxdatalake.PlexProd.raw_Part_v_Production` p
  JOIN `voxdatalake.PlexProd.raw_Part_v_Job_Op` o ON SAFE_CAST(o.Job_Op_Key AS INT64) = SAFE_CAST(p.Job_Op_Key AS INT64)
  JOIN `voxdatalake.PlexProd.raw_Part_v_Operation` op ON SAFE_CAST(op.Operation_Key AS INT64) = SAFE_CAST(o.Operation_Key AS INT64)
  WHERE op.Operation_Code = 'Labeling'
  GROUP BY 1
),
lab_open AS (
  SELECT SUM(GREATEST(j.job_qty - IFNULL(g.good_qty, 0), 0)) AS open_qty, COUNT(*) AS open_jobs
  FROM lab_ops l JOIN lab_jobs j USING (job_key) LEFT JOIN lab_good g USING (job_key)
)
SELECT a.sort_order, a.area, a.unit_label,
  IF(a.workcenter_group = 'Blending', (SELECT jobs FROM yday_blends), COALESCE(y.qty, 0)) AS yesterday_value,
  (SELECT yday FROM params) AS yesterday_date,
  a.today_value,
  g.actual_qty AS mtd_value, g.goal_value AS mtd_goal, g.pct_to_goal,
  SAFE_DIVIDE(EXTRACT(DAY FROM CURRENT_DATE('America/Denver')) - 1,
              EXTRACT(DAY FROM LAST_DAY(CURRENT_DATE('America/Denver')))) AS pct_of_month,
  IF(a.workcenter_group = 'Labeling', (SELECT open_qty FROM lab_open), a.open_value) AS open_value,
  IF(a.workcenter_group = 'Labeling', (SELECT open_jobs FROM lab_open), a.open_jobs) AS open_jobs,
  a.last_record_at
FROM `voxdatalake.PlexProd.production_area_summary_report` a
LEFT JOIN yday_qty y ON y.Workcenter_Group = a.workcenter_group
LEFT JOIN `voxdatalake.PlexProd.v2_production_vs_goal_report` g
  ON g.workcenter_group = a.workcenter_group
 AND g.production_month = DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH)
