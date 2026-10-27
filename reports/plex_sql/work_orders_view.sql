-- work_orders_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/work_orders_view.sql
-- confidence: high
-- plex_views: Part_v_Job_Op, Part_v_Job, Part_v_Workcenter, Part_v_Part, Part_v_Workcenter_Log
-- notes: Mechanical translation; SAFE_CAST/epoch date decoding dropped (native types), dates use CAST(x AS date).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per job operation (one workcenter step per production job).

WITH

-- Hours logged per job op. Workcenter_Event_Key NULL = normal run; NOT NULL = problem/downtime event.
actual_hours AS (
  SELECT
    wl.Job_Op_Key,
    SUM(wl.Log_Hours)                                                               AS actual_hours_total,
    SUM(CASE WHEN wl.Workcenter_Event_Key IS NULL     THEN wl.Log_Hours ELSE 0 END) AS productive_hours,
    SUM(CASE WHEN wl.Workcenter_Event_Key IS NOT NULL THEN wl.Log_Hours ELSE 0 END) AS downtime_hours
  FROM Part_v_Workcenter_Log AS wl
  GROUP BY wl.Job_Op_Key
)

SELECT
  j.Job_No                          AS job_no,
  jo.Op_No                          AS operation_no,
  p.Part_No                         AS part_no,
  p.Name                            AS part_name,
  wc.Name                           AS workcenter,
  wc.Workcenter_Type                AS workcenter_type,
  jo.Quantity                       AS qty,
  jo.Setup_Time                     AS setup_time_planned,
  jo.Fixed_Run_Time                 AS run_time_planned,
  ah.actual_hours_total,
  ah.productive_hours,
  ah.downtime_hours,
  CAST(jo.Start_Date    AS date)    AS op_start_date,
  CAST(jo.Complete_Date AS date)    AS op_completion_date,
  CAST(jo.Due_Date      AS date)    AS op_due_date,
  CAST(j.Due_Date       AS date)    AS job_due_date,
  CAST(j.Completed_Date AS date)    AS job_completed_date,
  CAST(j.Add_Date       AS date)    AS job_created_date,
  jo.Job_Op_Status_Key              AS job_op_status_key,
  j.Job_Status_Key                  AS job_status_key
FROM Part_v_Job_Op AS jo
JOIN Part_v_Job AS j
  ON jo.Job_Key = j.Job_Key
LEFT JOIN Part_v_Workcenter AS wc
  ON jo.Workcenter_Key = wc.Workcenter_Key
LEFT JOIN Part_v_Part AS p
  ON jo.Part_Key = p.Part_Key
LEFT JOIN actual_hours AS ah
  ON jo.Job_Op_Key = ah.Job_Op_Key;
