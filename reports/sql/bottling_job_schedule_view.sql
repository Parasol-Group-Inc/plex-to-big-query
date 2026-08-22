-- bottling_job_schedule_report — Vox Nutrition Bottling Job Schedule
--
-- ORIGIN: covers the Plex-sourceable columns of the manually maintained
-- "Bottling Job Schedule" Google Sheet (5 tabs analyzed: Open Liquids, Open
-- Powders, Open Gummies, Open Capsules_Softgels, and a populated "August
-- 2026" log — see spreadsheets/bottling_job_schedule.md for the full
-- column-by-column mapping). Same production-tracking pattern as MFG Job
-- Schedule, specialized to the Bottling step.
--
-- Not re-extracted — bq_view entry in reports/work_orders.yaml, same
-- extractions as work_orders_report/mfg_job_schedule_report (Part_v_Job,
-- Part_v_Job_Op, Part_v_Workcenter, Part_v_Job_Status, Personnel_v_Employee,
-- Part_v_Lot). PLACEHOLDERS: {gcp_project} and {dataset} are replaced at
-- runtime by the container using the GCP_PROJECT and BQ_DATASET env vars.
--
-- GRAIN: one row per job operation on a Bottling workcenter.
--
-- WORKCENTER FILTER: wc.Workcenter_Group = 'Bottling' — same confirmed live
-- roster used by packaging_daily_report_view.sql (Bottling Line 1-6, Bulk
-- Room, Powder Line, Liquid Line). The sheet's own 4 tabs (Liquids/Powders/
-- Gummies/Capsules_Softgels) do NOT have a confirmed Plex-side split (no
-- Part_Group/Product_Type mapping verified per tab) — this view returns the
-- whole Bottling roster undivided; splitting into per-tab views is an open
-- question, not guessed here.
--
-- COLUMN MAPPING (see spreadsheets/bottling_job_schedule.md for the full
-- buildable/gap/manual-only breakdown):
--   Bottle Count / Pill Count → Part_v_Job.Quantity (planned_qty)
--   Start Date / Finished date → Part_v_Job_Op.Start_Date/Complete_Date
--   LOT → Part_v_Job.Lot_Key → Part_v_Lot.Lot_No
--   Input Name → Job_Op.Started_By/Completed_By → Personnel_v_Employee.Common_Name
--     (ambiguous whether the sheet means the physical operator or the
--     data-entry person — both exposed, not collapsed into one column;
--     same INFERRED Plexus_User_No join as mfg_job_schedule_view.sql)
--
-- NOT built (see doc for why): Rep (needs a confirmed SO#→Sales_v_PO link
-- that doesn't exist), Bottle/Lid Size and Color and Fill Weight (plausible
-- Part_v_BOM leads, unit-conversion/component-mapping unconfirmed), SO#/WO#
-- (NetSuite-native, no Plex FK), and all manual-only columns (Date Entered,
-- Picked, Sign Off, PALLET, Notes, Status).
--
-- RUN TIME / # COMPLETED — the doc's most promising new lead, built here as
-- an exploratory reconstruction, NOT confirmed against real data (Job_Op
-- was empty on the test tenant at build time, same as every other Daily
-- Report in this family):
--   op_qty            — Job_Op.Quantity, candidate for "# Completed"
--   run_time_minutes  — op_completion_ts - op_start_ts, candidate for
--                        "Run Time" (sheet shows clock ranges like 8:56-10:25)
--
-- TIMESTAMP CONVERSION PATTERN (this view only): every other view in this
-- repo truncates the raw Start_Date/Complete_Date columns straight to DATE
-- (see the "DATE CONVERSION PATTERN" comment in work_orders_view.sql) since
-- none of them need time-of-day. Run Time reconstruction needs it, so this
-- view keeps full TIMESTAMP precision instead — same INT64-nanoseconds /
-- STRING dual-path handling, just without the final truncation to DATE.
-- op_start_date/op_completion_date (plain DATE, matching the sheet's Start
-- Date/Finished date columns) are derived from the same timestamps below.

WITH base AS (
  SELECT

    -- ── Job / operation identity ──────────────────────────────────────────
    j.Job_No                                        AS job_no,
    SAFE_CAST(jo.Op_No AS INT64)                    AS operation_no,
    p.Part_No                                       AS part_no,
    p.Name                                          AS part_name,

    -- ── Workcenter ─────────────────────────────────────────────────────────
    wc.Name                                         AS workcenter,

    -- ── Bottle/Pill Count (job-level planned quantity) ────────────────────
    SAFE_CAST(j.Quantity AS FLOAT64)                AS planned_qty,

    -- ── Status (text, not just key) ───────────────────────────────────────
    js.Job_Status                                   AS job_status,
    SAFE_CAST(js.Completed_Status AS INT64)          AS job_status_is_completed,
    SAFE_CAST(js.Cancelled_Status AS INT64)          AS job_status_is_cancelled,

    -- ── Input Name candidates (ambiguous — see header note) ────────────────
    started_emp.Common_Name                         AS started_by_name,
    completed_emp.Common_Name                       AS completed_by_name,

    -- ── Operation timestamps (full precision — see TIMESTAMP CONVERSION
    --    PATTERN above) ───────────────────────────────────────────────────
    COALESCE(
      NULLIF(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(jo.Start_Date AS STRING) AS INT64), 0), 1000)), TIMESTAMP '1970-01-01 00:00:00'),
      NULLIF(SAFE_CAST(CAST(jo.Start_Date AS STRING) AS TIMESTAMP), TIMESTAMP '1970-01-01 00:00:00')
    )                                                AS op_start_ts,
    COALESCE(
      NULLIF(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(jo.Complete_Date AS STRING) AS INT64), 0), 1000)), TIMESTAMP '1970-01-01 00:00:00'),
      NULLIF(SAFE_CAST(CAST(jo.Complete_Date AS STRING) AS TIMESTAMP), TIMESTAMP '1970-01-01 00:00:00')
    )                                                AS op_completion_ts,

    -- ── # Completed reconstruction lead (exploratory — see header) ────────
    SAFE_CAST(jo.Quantity AS FLOAT64)               AS op_qty,

    -- ── Lot ────────────────────────────────────────────────────────────────
    lot.Lot_No                                      AS lot_no

  FROM `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo

  JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
    ON jo.Job_Key = j.Job_Key

  JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
    ON SAFE_CAST(jo.Workcenter_Key AS INT64) = wc.Workcenter_Key

  -- raw_Part_v_Part is shared with the sales_orders pipeline — not re-extracted here.
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
    ON SAFE_CAST(jo.Part_Key AS INT64) = p.Part_Key

  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Status` js
    ON SAFE_CAST(j.Job_Status_Key AS INT64) = js.Job_Status_Key

  LEFT JOIN `{gcp_project}.{dataset}.raw_Personnel_v_Employee` started_emp
    ON SAFE_CAST(jo.Started_By AS INT64) = started_emp.Plexus_User_No

  LEFT JOIN `{gcp_project}.{dataset}.raw_Personnel_v_Employee` completed_emp
    ON SAFE_CAST(jo.Completed_By AS INT64) = completed_emp.Plexus_User_No

  -- SAFE_CAST both sides: raw_Part_v_Lot is empty on the test tenant, so
  -- BigQuery typed it all-STRING — same situation as mfg_job_schedule_view.sql.
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Lot` lot
    ON SAFE_CAST(j.Lot_Key AS INT64) = SAFE_CAST(lot.Lot_Key AS INT64)

  WHERE wc.Workcenter_Group = 'Bottling'
)

SELECT
  job_no,
  operation_no,
  part_no,
  part_name,
  workcenter,
  planned_qty,
  job_status,
  job_status_is_completed,
  job_status_is_cancelled,
  started_by_name,
  completed_by_name,
  DATE(op_start_ts)                                 AS op_start_date,
  DATE(op_completion_ts)                            AS op_completion_date,
  op_start_ts,
  op_completion_ts,
  TIMESTAMP_DIFF(op_completion_ts, op_start_ts, MINUTE)
                                                     AS run_time_minutes,
  op_qty,
  lot_no

FROM base
