-- printing_open_work_orders_report — Plex-native rebuild of NetSuite's
-- "Printing Open Work Orders" saved search (reports-list/sales.md)
--
-- Same shape as labeling_open_work_orders_view.sql (see that file for the
-- full origin/status-mapping notes) — this is that view with the workcenter
-- pattern swapped from 'Labeling Line%' to 'Printing%'.
--
-- CONFIRMED LIVE (2026-08-11, same pass that confirmed the Labeling
-- workcenters): 'Printing' exists as a live Workcenter_Type='Primary'
-- workcenter on this tenant.
--
-- STATUS MAPPING (inferred, not NetSuite-confirmed, same assumption as the
-- Labeling report): "open" = inverse of Completed/Cancelled/Hold flags on
-- Part_v_Job_Status, not a specific NetSuite status-text match — no
-- screenshot of this saved search's actual criteria was available.
--
-- GRAIN: one row per job operation on the Printing workcenter.

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

WHERE wc.Name LIKE 'Printing%'
  AND COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Hold_Status AS INT64), 0) = 0
