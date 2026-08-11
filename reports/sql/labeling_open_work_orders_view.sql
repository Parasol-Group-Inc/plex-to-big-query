-- labeling_open_work_orders_report — Plex-native rebuild of NetSuite's
-- "Labeling | Open WO: Results" saved search (searchid=2555)
--
-- HOW TO EDIT (no deployment required):
--   gcloud storage cp reports/sql/labeling_open_work_orders_view.sql gs://voxdatalake-report-configs/sql/
--   The next pipeline run will recreate the view with the updated SQL.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- ORIGIN: reports-list/production.md — "Labeling | Open WO: Results" was
-- first marked out-of-scope (NetSuite-native saved search), then
-- reconsidered after seeing its actual NetSuite criteria (screenshot,
-- 2026-08-11): Type=Work Order, Status IN (Released, In Process),
-- Item:Class=Labeling, Item:Name NOT CONTAINS 'lot traced'. The underlying
-- business question ("which jobs are open and need labeling") maps to
-- Plex's own Job/Job_Op + Workcenter data — no need to touch NetSuite.
--
-- GRAIN: one row per job operation on a Labeling Line workcenter.
--
-- CONFIRMED LIVE (2026-08-11) workcenter naming on this tenant:
-- 'Labeling Line 1' through 'Labeling Line 6' (Workcenter_Type = 'Primary').
-- Also resolved in this same query: 'Label Approval'/'Label Design'
-- (Workcenter_Type = 'Simplified') are a DIFFERENT workflow step (label
-- artwork approval, not physical labeling production) — intentionally
-- excluded by the 'Labeling Line%' pattern below.
--
-- STATUS MAPPING (inferred, not NetSuite-confirmed): NetSuite's
-- "Released, In Process" ~ Plex Job_Status 'Scheduled'/'Production'.
-- Implemented as the inverse of Completed/Cancelled/Hold flags instead of
-- matching status text directly, so it doesn't silently go stale if this
-- tenant adds more status values.
--
-- NOT MAPPED (gap, not guessed): NetSuite's "Item: Name does not contain
-- 'lot traced'" exclusion has no confirmed Plex equivalent. Omitted rather
-- than approximated — if this matters, it needs its own investigation
-- (likely Part_v_Part_Attribute or a naming convention on Part_v_Part.Name).

SELECT

  j.Job_No                                        AS job_no,
  p.Part_No                                       AS part_no,
  p.Name                                          AS part_name,
  wc.Name                                         AS workcenter,
  js.Job_Status                                   AS job_status,
  SAFE_CAST(jo.Quantity AS FLOAT64)               AS qty,

  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(jo.Due_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(jo.Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(jo.Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS op_due_date,

  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(jo.Start_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(jo.Start_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(jo.Start_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS op_start_date

FROM `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo

JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
  ON jo.Job_Key = j.Job_Key

JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
  ON SAFE_CAST(jo.Workcenter_Key AS INT64) = wc.Workcenter_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(jo.Part_Key AS INT64) = p.Part_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Status` js
  ON SAFE_CAST(j.Job_Status_Key AS INT64) = js.Job_Status_Key

WHERE wc.Name LIKE 'Labeling Line%'
  AND COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Hold_Status AS INT64), 0) = 0
