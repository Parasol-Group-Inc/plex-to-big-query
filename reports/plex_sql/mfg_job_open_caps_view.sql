-- mfg_job_open_caps_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/mfg_job_open_caps_view.sql
-- confidence: high
-- plex_views: Part_v_Job_Op, Part_v_Job, Part_v_Workcenter, Part_v_Part, Part_v_Job_Status
-- notes: Mechanical translation; SAFE_CAST/epoch date decoding dropped, dates use CAST(x AS date).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per open job that has an Encapsulating operation (DISTINCT collapses multiple ops).
-- "Open" = job status is not Completed, Cancelled or On Hold.

SELECT DISTINCT
  j.Job_No                  AS job_no,
  p.Part_No                 AS part_no,
  p.Name                    AS part_name,
  js.Job_Status             AS job_status,
  j.Quantity                AS caps_pending,
  CAST(j.Add_Date AS date)  AS date_entered
FROM Part_v_Job_Op AS jo
JOIN Part_v_Job AS j
  ON jo.Job_Key = j.Job_Key
JOIN Part_v_Workcenter AS wc
  ON jo.Workcenter_Key = wc.Workcenter_Key
LEFT JOIN Part_v_Part AS p
  ON j.Part_Key = p.Part_Key
LEFT JOIN Part_v_Job_Status AS js
  ON j.Job_Status_Key = js.Job_Status_Key
WHERE wc.Workcenter_Group = 'Encapsulating'
  AND ISNULL(js.Completed_Status, 0) = 0
  AND ISNULL(js.Cancelled_Status, 0) = 0
  AND ISNULL(js.Hold_Status, 0) = 0;
