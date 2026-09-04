-- mfg_job_open_caps_report — pending quantity for open Encapsulation jobs
-- (Plex-native candidate for the Vox Nutrition Scorecard's MFG_Job "Open
-- Caps" Operations tile — see score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- Mirrors labeling_open_work_orders_view.sql's proven pattern exactly:
-- same "open" definition (inverse of Completed/Cancelled/Hold status
-- flags — decided 2026-09-01 to match the existing Labeling/Printing Open
-- WO reports rather than a brittle status-text match), same join shape,
-- different workcenter roster. This directly fixes the gap the scorecard
-- audit itself flagged: the original sheet's "Caps Pending" chart summed
-- with no status filter applied at all.
--
-- WORKCENTER MAPPING: 'Encapsulation%' text match, same confirmed-live
-- roster ('Encapsulation 1' through 'Encapsulation 10') already used by
-- encap_daily_report_view.sql's Workcenter_Group = 'Encapsulating' filter.
--
-- CAPS PENDING = the still-open job's planned quantity (Part_v_Job.Quantity).
-- SELECT DISTINCT on job_no avoids double-counting a job that has multiple
-- operations/rows on this workcenter.
--
-- Not re-extracted — bq_view entry in reports/work_orders.yaml, same raw
-- tables as labeling_open_work_orders_report.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per open job on an Encapsulation workcenter.

SELECT DISTINCT

  j.Job_No                                        AS job_no,
  p.Part_No                                       AS part_no,
  p.Name                                          AS part_name,
  js.Job_Status                                   AS job_status,
  SAFE_CAST(j.Quantity AS FLOAT64)                AS caps_pending,

  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(j.Add_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(j.Add_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(j.Add_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS date_entered

FROM `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo

JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
  ON SAFE_CAST(jo.Job_Key AS INT64) = SAFE_CAST(j.Job_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
  ON SAFE_CAST(jo.Workcenter_Key AS INT64) = wc.Workcenter_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(j.Part_Key AS INT64) = p.Part_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Status` js
  ON SAFE_CAST(j.Job_Status_Key AS INT64) = SAFE_CAST(js.Job_Status_Key AS INT64)

WHERE wc.Name LIKE 'Encapsulation%'
  AND COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Hold_Status AS INT64), 0) = 0
