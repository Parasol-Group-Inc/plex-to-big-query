-- mfg_job_schedule_report — Vox Nutrition MFG production schedule detail
--
-- HOW TO EDIT (no deployment required):
--   gcloud storage cp reports/sql/mfg_job_schedule_view.sql gs://voxdatalake-report-configs/sql/
--   The next pipeline run will recreate the view with the updated SQL.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
-- Do NOT hardcode project or dataset names here.
--
-- ORIGIN: built to cover the Plex-sourceable columns of a manually maintained
-- "MFG Job Schedule" tracking spreadsheet (blending/encap timestamps, lot,
-- QC status, equipment, room). See docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md for
-- the full column-by-column mapping and what was deliberately excluded
-- (NetSuite WO numbers, and manual-only columns like Notes/Sign-Off/Days Left).
--
-- GRAIN: one row per job operation — same grain as work_orders_report, which
-- this view is a sibling of (both read raw_Part_v_Job / raw_Part_v_Job_Op /
-- raw_Part_v_Workcenter / raw_Part_v_Part; this view adds the columns that
-- work_orders_report doesn't cover: job status text, operator name, lot,
-- QC checksheet status, equipment/asset, building/room).
--
-- KEY JOINS (confirmed live against vox.test.odbc.plex.com 2026-08-11 —
-- SQL compiles and every join key/column exists; the test tenant itself had
-- no rows in these tables, so match RATES are unverified, only shapes):
--   Part_v_Job_Status        — Job_Status_Key -> text label + status flags
--   Personnel_v_Employee     — Started_By/Completed_By -> operator name.
--     INFERRED join: Job_Op.Started_By/Completed_By are assumed to be
--     Plexus_User_No values, by analogy with the already-confirmed
--     Sales_v_Order_Salesperson.Plexus_User_No -> Plexus_Control_v_Plexus_User
--     pattern used in reports/sql/sales_orders_view.sql. Not literally
--     confirmed (both tables were empty at check time).
--   Part_v_Lot               — Job.Lot_Key -> lot number + manufactured date
--   Part_v_Lot_Shelf_Life    — Lot_Key -> raw shelf-life value. Deliberately
--     NOT converted into an expiration date: Shelf_Life_Type_Key's unit
--     (days? a formatted duration?) is unconfirmed without live sample data.
--   Quality_v_Checksheet(_Status) — Job_Op_Key -> most recent QC inspection
--     result for that operation. Closest available analog to the manual
--     tracker's "Raw Material in Testing" / "Raws Released" columns — it's
--     a status-flag join, not a literal text match, and Checksheet is
--     part/operation-level QC, not specifically "raw material received" QC.
--   Maintenance_v_Equipment  — Workcenter_Key -> asset ID for that operation
--   Common_v_Building        — Job.Building_Key -> room/building

WITH

-- One row per job operation, keeping only the most recent QC checksheet
-- result (a job op can have multiple inspections over time).
latest_checksheet AS (
  SELECT
    Job_Op_Key,
    Checksheet_No,
    Checksheet_Status_Key,
    Inspection_Date,
    Out_Of_Spec,
    ROW_NUMBER() OVER (
      PARTITION BY SAFE_CAST(Job_Op_Key AS INT64)
      ORDER BY SAFE_CAST(CAST(Inspection_Date AS STRING) AS TIMESTAMP) DESC
    ) AS rn
  FROM `{gcp_project}.{dataset}.raw_Quality_v_Checksheet`
)

SELECT

  -- ── Job / operation identity ────────────────────────────────────────────────
  j.Job_No                                        AS job_no,
  SAFE_CAST(jo.Op_No AS INT64)                    AS operation_no,
  p.Part_No                                       AS part_no,
  p.Name                                          AS part_name,
  SAFE_CAST(jo.Quantity AS FLOAT64)               AS qty,

  -- ── Workcenter / equipment / room ───────────────────────────────────────────
  wc.Name                                         AS workcenter,
  wc.Workcenter_Type                              AS workcenter_type,
  eq.Equipment_ID                                 AS asset_id,
  bldg.Name                                       AS room,

  -- ── Status (text, not just key) ─────────────────────────────────────────────
  js.Job_Status                                   AS job_status,
  SAFE_CAST(js.Completed_Status AS INT64)         AS job_status_is_completed,
  SAFE_CAST(js.Cancelled_Status AS INT64)         AS job_status_is_cancelled,

  -- ── Operator (name, resolved from Started_By/Completed_By) ─────────────────
  started_emp.Common_Name                         AS started_by_name,
  completed_emp.Common_Name                       AS completed_by_name,

  -- ── Operation dates (planned + actual) ──────────────────────────────────────
  -- Same date-conversion pattern as work_orders_view.sql: raw columns can be
  -- INT64 nanoseconds, TIMESTAMP, or STRING depending on pipeline history.
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(jo.Start_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(jo.Start_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(jo.Start_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS op_start_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(jo.Complete_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(jo.Complete_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(jo.Complete_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS op_completion_date,

  -- ── Lot ──────────────────────────────────────────────────────────────────────
  lot.Lot_No                                      AS lot_no,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(lot.Manufactured_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(lot.Manufactured_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(lot.Manufactured_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS lot_manufactured_date,
  SAFE_CAST(shelf.Lot_Shelf_Life AS FLOAT64)      AS lot_shelf_life_raw,

  -- ── QC / checksheet status (most recent inspection for this operation) ──────
  lc.Checksheet_No                                AS checksheet_no,
  cs_status.Checksheet_Status                     AS checksheet_status,
  SAFE_CAST(cs_status.Approved AS INT64)          AS checksheet_is_approved,
  SAFE_CAST(cs_status.Rejected AS INT64)          AS checksheet_is_rejected,
  SAFE_CAST(lc.Out_Of_Spec AS INT64)              AS checksheet_out_of_spec

FROM `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo

JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
  ON jo.Job_Key = j.Job_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
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

-- SAFE_CAST both sides on these three joins: Part_v_Lot, Part_v_Lot_Shelf_Life,
-- and Maintenance_v_Equipment are all empty on this tenant, so BigQuery
-- created them with all-STRING schema — the left side (a populated table)
-- is already INT64, so a one-sided cast would compile but never match.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Lot` lot
  ON SAFE_CAST(j.Lot_Key AS INT64) = SAFE_CAST(lot.Lot_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Lot_Shelf_Life` shelf
  ON SAFE_CAST(j.Lot_Key AS INT64) = SAFE_CAST(shelf.Lot_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Maintenance_v_Equipment` eq
  ON SAFE_CAST(jo.Workcenter_Key AS INT64) = SAFE_CAST(eq.Workcenter_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Building` bldg
  ON SAFE_CAST(j.Building_Key AS INT64) = bldg.Building_Key

LEFT JOIN latest_checksheet lc
  ON SAFE_CAST(jo.Job_Op_Key AS INT64) = SAFE_CAST(lc.Job_Op_Key AS INT64)
  AND lc.rn = 1

LEFT JOIN `{gcp_project}.{dataset}.raw_Quality_v_Checksheet_Status` cs_status
  ON SAFE_CAST(lc.Checksheet_Status_Key AS INT64) = cs_status.Checksheet_Status_Key
