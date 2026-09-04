-- bottling_job_open_report — pending quantity for open Bottling jobs
-- (Plex-native candidate for the Vox Nutrition Scorecard's Bottling_Job
-- "Open Bottles" Operations tile — see score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- Same pattern and "open" definition as mfg_job_open_caps_report (this
-- file's sibling) — see that file's header for the full rationale. Fixes
-- the same no-status-filter gap the scorecard audit flagged, for Bottling
-- instead of Encapsulation.
--
-- WORKCENTER MAPPING: Workcenter_Group = 'Bottling', same confirmed-live
-- group already used by bottling_job_schedule_view.sql and
-- packaging_daily_report_view.sql.
--
-- Not re-extracted — bq_view entry in reports/work_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per open job on a Bottling workcenter.

SELECT DISTINCT

  j.Job_No                                        AS job_no,
  p.Part_No                                       AS part_no,
  p.Name                                          AS part_name,
  js.Job_Status                                   AS job_status,
  SAFE_CAST(j.Quantity AS FLOAT64)                AS qty_pending,

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

WHERE wc.Workcenter_Group = 'Bottling'
  AND COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Hold_Status AS INT64), 0) = 0
