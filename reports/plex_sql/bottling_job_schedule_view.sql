-- bottling_job_schedule_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/bottling_job_schedule_view.sql
-- confidence: high
-- plex_views: Part_v_Job_Op, Part_v_Job, Part_v_Workcenter, Part_v_Part, Part_v_Job_Status, Personnel_v_Employee, Part_v_Lot
-- notes: Mechanical translation; TIMESTAMP_DIFF(MINUTE) becomes DATEDIFF(minute); Plex timestamps are local time, BigQuery's may be UTC-shifted.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per job operation on a Bottling-group workcenter.

WITH base AS (
  SELECT
    j.Job_No                  AS job_no,
    jo.Op_No                  AS operation_no,
    p.Part_No                 AS part_no,
    p.Name                    AS part_name,
    wc.Name                   AS workcenter,
    j.Quantity                AS planned_qty,
    js.Job_Status             AS job_status,
    js.Completed_Status       AS job_status_is_completed,
    js.Cancelled_Status       AS job_status_is_cancelled,
    started_emp.Common_Name   AS started_by_name,
    completed_emp.Common_Name AS completed_by_name,
    jo.Start_Date             AS op_start_ts,
    jo.Complete_Date          AS op_completion_ts,
    jo.Quantity               AS op_qty,
    lot.Lot_No                AS lot_no
  FROM Part_v_Job_Op AS jo
  JOIN Part_v_Job AS j
    ON jo.Job_Key = j.Job_Key
  JOIN Part_v_Workcenter AS wc
    ON jo.Workcenter_Key = wc.Workcenter_Key
  LEFT JOIN Part_v_Part AS p
    ON jo.Part_Key = p.Part_Key
  LEFT JOIN Part_v_Job_Status AS js
    ON j.Job_Status_Key = js.Job_Status_Key
  LEFT JOIN Personnel_v_Employee AS started_emp
    ON jo.Started_By = started_emp.Plexus_User_No
  LEFT JOIN Personnel_v_Employee AS completed_emp
    ON jo.Completed_By = completed_emp.Plexus_User_No
  LEFT JOIN Part_v_Lot AS lot
    ON j.Lot_Key = lot.Lot_Key
  WHERE wc.Workcenter_Group = 'Bottling'
)

SELECT
  b.job_no,
  b.operation_no,
  b.part_no,
  b.part_name,
  b.workcenter,
  b.planned_qty,
  b.job_status,
  b.job_status_is_completed,
  b.job_status_is_cancelled,
  b.started_by_name,
  b.completed_by_name,
  CAST(b.op_start_ts AS date)      AS op_start_date,
  CAST(b.op_completion_ts AS date) AS op_completion_date,
  b.op_start_ts,
  b.op_completion_ts,
  DATEDIFF(minute, b.op_start_ts, b.op_completion_ts) AS run_time_minutes,
  b.op_qty,
  b.lot_no
FROM base AS b;
