-- work_orders_report — Vox Nutrition production work orders by workcenter
--
-- HOW TO EDIT (no deployment required):
--   gcloud storage cp reports/sql/work_orders_view.sql gs://voxdatalake-report-configs/sql/
--   The next pipeline run will recreate the view with the updated SQL.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
-- Do NOT hardcode project or dataset names here.
--
-- GRAIN: one row per job operation (one workcenter step per production job).
-- A single job (Job_No) appears multiple times — once per operation (Op_No).
--
-- KEY JOINS (confirmed against live Plex schema 2026-07-13):
--   Part_v_Job_Op     → primary fact: qty, planned times, actual dates, workcenter
--   Part_v_Job        → job header: Job_No, overall status, due/completed dates
--   Part_v_Workcenter → workcenter name + type (Workcenter_Type is inline — no extra join)
--   Part_v_Part       → part number and name
--   Part_v_Workcenter_Log → actual hours logged per job op (SUM on Job_Op_Key)
--
-- NOTE: In Plex, "Work Orders" (Part_v_Work_Order) and "Jobs" (Part_v_Job) are
-- separate entities with no direct FK between them in the ODBC views. Jobs are
-- the shop-floor execution records with actual production data. This report uses
-- Jobs as the primary entity.
--
-- SAFE_CAST: Part_v_Job, Part_v_Job_Op, and Part_v_Workcenter_Log had no records
-- in the test environment — BigQuery created those tables with all-STRING schema.
-- SAFE_CAST handles type compatibility when tables populate with real production data.
-- It is a no-op when the column is already the correct type.

WITH

-- Actual hours logged by operators, split by event type.
-- Workcenter_Event_Key IS NULL     → normal production run (no problem triggered)
-- Workcenter_Event_Key IS NOT NULL → problem/downtime event (Conveyor Problem,
--   Lube Problem, Material Defect, Injury, No Raw Material, etc.)
-- Confirmed 2026-07-13: all Part_v_Workcenter_Event rows are problem events.
actual_hours AS (
  SELECT
    Job_Op_Key,
    SUM(SAFE_CAST(Log_Hours AS FLOAT64))                                          AS actual_hours_total,
    SUM(CASE WHEN Workcenter_Event_Key IS NULL
             THEN SAFE_CAST(Log_Hours AS FLOAT64) ELSE 0 END)                     AS productive_hours,
    SUM(CASE WHEN Workcenter_Event_Key IS NOT NULL
             THEN SAFE_CAST(Log_Hours AS FLOAT64) ELSE 0 END)                     AS downtime_hours
  FROM `{gcp_project}.{dataset}.raw_Part_v_Workcenter_Log`
  GROUP BY Job_Op_Key
)

SELECT

  -- ── Job info ────────────────────────────────────────────────────────────────
  j.Job_No                                        AS job_no,
  SAFE_CAST(jo.Op_No AS INT64)                    AS operation_no,

  -- ── Part ────────────────────────────────────────────────────────────────────
  p.Part_No                                       AS part_no,
  p.Name                                          AS part_name,

  -- ── Workcenter ──────────────────────────────────────────────────────────────
  -- Workcenter_Type is a string directly on Part_v_Workcenter (no lookup join needed).
  -- Confirmed values from live data: Batch, Bin for Bin, Kanban, etc.
  wc.Name                                         AS workcenter,
  wc.Workcenter_Type                              AS workcenter_type,

  -- ── Quantity ────────────────────────────────────────────────────────────────
  SAFE_CAST(jo.Quantity AS FLOAT64)               AS qty,

  -- ── Time (planned, from job operation routing) ──────────────────────────────
  SAFE_CAST(jo.Setup_Time AS FLOAT64)             AS setup_time_planned,
  SAFE_CAST(jo.Fixed_Run_Time AS FLOAT64)         AS run_time_planned,

  -- ── Time (actual, from operator workcenter log entries) ─────────────────────
  -- productive_hours: Workcenter_Event_Key IS NULL (normal production run)
  -- downtime_hours:   Workcenter_Event_Key IS NOT NULL (Conveyor Problem, Lube
  --                   Problem, Material Defect, Injury, No Raw Material, etc.)
  -- Compare productive_hours vs run_time_planned for efficiency analysis.
  ah.actual_hours_total,
  ah.productive_hours,
  ah.downtime_hours,

  -- ── Operation dates ─────────────────────────────────────────────────────────
  -- Plex date columns arrive as INT64 nanoseconds (pyodbc datetime → pandas
  -- datetime64[ns] → BQ int64). NULLIF(...,0) converts Plex's "no date"
  -- sentinel to NULL. COALESCE fallback handles STRING schema on empty tables.
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(jo.Start_Date    AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(jo.Start_Date    AS DATE), DATE '1970-01-01')
  )                                               AS op_start_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(jo.Complete_Date AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(jo.Complete_Date AS DATE), DATE '1970-01-01')
  )                                               AS op_completion_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(jo.Due_Date      AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(jo.Due_Date      AS DATE), DATE '1970-01-01')
  )                                               AS op_due_date,

  -- ── Job-level dates ─────────────────────────────────────────────────────────
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(j.Due_Date       AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(j.Due_Date       AS DATE), DATE '1970-01-01')
  )                                               AS job_due_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(j.Completed_Date AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(j.Completed_Date AS DATE), DATE '1970-01-01')
  )                                               AS job_completed_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(j.Add_Date       AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(j.Add_Date       AS DATE), DATE '1970-01-01')
  )                                               AS job_created_date,

  -- ── Status keys ─────────────────────────────────────────────────────────────
  -- Part_v_Work_Order_Op_Status had no records on test — status labels unavailable.
  -- Keys are preserved for filtering; add a JOIN if Plex populates the lookup table.
  SAFE_CAST(jo.Job_Op_Status_Key AS INT64)        AS job_op_status_key,
  SAFE_CAST(j.Job_Status_Key AS INT64)            AS job_status_key

FROM `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo

-- Job header — INNER JOIN: every op must have a parent job
JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
  ON jo.Job_Key = j.Job_Key

-- Workcenter name and type
-- Part_v_Workcenter had live data → Workcenter_Key is INT64; Job_Op is STRING (empty table)
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
  ON SAFE_CAST(jo.Workcenter_Key AS INT64) = wc.Workcenter_Key

-- raw_Part_v_Part is owned by the sales_orders pipeline (runs 2 h before this job).
-- Part_v_Part has live data → Part_Key is INT64; Job_Op.Part_Key is STRING.
-- Part_v_Part is NOT re-extracted by work_orders to avoid WRITE_TRUNCATE collision.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(jo.Part_Key AS INT64) = p.Part_Key

-- SAFE_CAST both sides: Job_Op becomes INT64 when populated; Workcenter_Log
-- may still be STRING if it stays empty (no log entries in test). Casting
-- both to INT64 is a no-op when the column is already the correct type.
LEFT JOIN actual_hours ah
  ON SAFE_CAST(jo.Job_Op_Key AS INT64) = SAFE_CAST(ah.Job_Op_Key AS INT64)
