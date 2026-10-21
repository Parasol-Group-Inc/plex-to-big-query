-- mfg_job_schedule_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/mfg_job_schedule_view.sql
-- confidence: high
-- plex_views: Part_v_Job_Op, Part_v_Job, Part_v_Workcenter, Part_v_Part, Part_v_Part_Product_Type, Part_v_Job_Status, Personnel_v_Employee, Part_v_Lot, Part_v_Lot_Shelf_Life, Maintenance_v_Equipment, Common_v_Building, Quality_v_Checksheet, Quality_v_Checksheet_Status, Part_v_Job_Type, Part_v_Job_Distribution
-- notes: Mechanical translation; yield_meets_goal/tat_meets_goal become 1/0/NULL instead of TRUE/FALSE/NULL; lot_shelf_life_raw is CAST to varchar.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per job operation.
-- Goal checks are exploratory: yield >= 0.95 (Stock) / 0.92 (other); total days <= 84.

WITH

-- Most recent QC checksheet per job op.
latest_checksheet AS (
  SELECT
    cs.Job_Op_Key,
    cs.Checksheet_No,
    cs.Checksheet_Status_Key,
    cs.Inspection_Date,
    cs.Out_Of_Spec,
    ROW_NUMBER() OVER (PARTITION BY cs.Job_Op_Key ORDER BY cs.Inspection_Date DESC) AS rn
  FROM Quality_v_Checksheet AS cs
),

-- One row per job: a distribution count plus one sample Release_Key.
job_distribution_summary AS (
  SELECT
    jd.Job_Key,
    COUNT(*)            AS distribution_count,
    MIN(jd.Release_Key) AS sample_release_key
  FROM Part_v_Job_Distribution AS jd
  GROUP BY jd.Job_Key
),

base AS (
  SELECT
    j.Job_No                            AS job_no,
    jo.Op_No                            AS operation_no,
    p.Part_No                           AS part_no,
    p.Name                              AS part_name,
    pt.Product_Type                     AS part_product_type,
    jo.Quantity                         AS qty,
    j.Quantity                          AS planned_qty,
    wc.Name                             AS workcenter,
    wc.Workcenter_Type                  AS workcenter_type,
    eq.Equipment_ID                     AS asset_id,
    bldg.Name                           AS room,
    js.Job_Status                       AS job_status,
    js.Completed_Status                 AS job_status_is_completed,
    js.Cancelled_Status                 AS job_status_is_cancelled,
    started_emp.Common_Name             AS started_by_name,
    completed_emp.Common_Name           AS completed_by_name,
    CAST(jo.Start_Date    AS date)      AS op_start_date,
    CAST(jo.Complete_Date AS date)      AS op_completion_date,
    lot.Lot_No                          AS lot_no,
    CAST(lot.Manufactured_Date AS date) AS lot_manufactured_date,
    CAST(shelf.Lot_Shelf_Life AS varchar(50)) AS lot_shelf_life_raw,
    lc.Checksheet_No                    AS checksheet_no,
    cs_status.Checksheet_Status         AS checksheet_status,
    cs_status.Approved                  AS checksheet_is_approved,
    cs_status.Rejected                  AS checksheet_is_rejected,
    lc.Out_Of_Spec                      AS checksheet_out_of_spec,
    CAST(lc.Inspection_Date AS date)    AS checksheet_inspection_date,
    jt.Job_Type                         AS job_type,
    jds.distribution_count              AS job_distribution_count,
    jds.sample_release_key              AS job_distribution_sample_release_key,
    CAST(j.Add_Date AS date)            AS job_add_date
  FROM Part_v_Job_Op AS jo
  JOIN Part_v_Job AS j
    ON jo.Job_Key = j.Job_Key
  LEFT JOIN Part_v_Workcenter AS wc
    ON jo.Workcenter_Key = wc.Workcenter_Key
  LEFT JOIN Part_v_Part AS p
    ON jo.Part_Key = p.Part_Key
  LEFT JOIN Part_v_Part_Product_Type AS pt
    ON p.Product_Type_Key = pt.Product_Type_Key
  LEFT JOIN Part_v_Job_Status AS js
    ON j.Job_Status_Key = js.Job_Status_Key
  -- Started_By / Completed_By assumed to be Plexus_User_No (inferred, not confirmed).
  LEFT JOIN Personnel_v_Employee AS started_emp
    ON jo.Started_By = started_emp.Plexus_User_No
  LEFT JOIN Personnel_v_Employee AS completed_emp
    ON jo.Completed_By = completed_emp.Plexus_User_No
  LEFT JOIN Part_v_Lot AS lot
    ON j.Lot_Key = lot.Lot_Key
  LEFT JOIN Part_v_Lot_Shelf_Life AS shelf
    ON j.Lot_Key = shelf.Lot_Key
  LEFT JOIN Maintenance_v_Equipment AS eq
    ON jo.Workcenter_Key = eq.Workcenter_Key
  LEFT JOIN Common_v_Building AS bldg
    ON j.Building_Key = bldg.Building_Key
  LEFT JOIN latest_checksheet AS lc
    ON jo.Job_Op_Key = lc.Job_Op_Key
   AND lc.rn = 1
  LEFT JOIN Quality_v_Checksheet_Status AS cs_status
    ON lc.Checksheet_Status_Key = cs_status.Checksheet_Status_Key
  LEFT JOIN Part_v_Job_Type AS jt
    ON j.Job_Type_Key = jt.Job_Type_Key
  LEFT JOIN job_distribution_summary AS jds
    ON j.Job_Key = jds.Job_Key
)

SELECT
  b.*,
  b.qty / NULLIF(b.planned_qty, 0) AS yield_pct,
  -- 1 = meets goal, 0 = misses, NULL = not computable (BigQuery returns TRUE/FALSE/NULL)
  CASE
    WHEN b.qty / NULLIF(b.planned_qty, 0) IS NULL THEN NULL
    WHEN b.job_type = 'Stock' THEN CASE WHEN b.qty / NULLIF(b.planned_qty, 0) >= 0.95 THEN 1 ELSE 0 END
    ELSE CASE WHEN b.qty / NULLIF(b.planned_qty, 0) >= 0.92 THEN 1 ELSE 0 END
  END AS yield_meets_goal,
  DATEDIFF(day, b.job_add_date, b.checksheet_inspection_date) AS total_days_from_job_creation,
  CASE
    WHEN DATEDIFF(day, b.job_add_date, b.checksheet_inspection_date) IS NULL THEN NULL
    WHEN DATEDIFF(day, b.job_add_date, b.checksheet_inspection_date) <= 84 THEN 1
    ELSE 0
  END AS tat_meets_goal
FROM base AS b;
