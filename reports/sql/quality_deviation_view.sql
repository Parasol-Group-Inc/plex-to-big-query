-- quality_deviation_report — Vox Nutrition Quality Deviations, correlated to
-- Jobs, Problems (NCs), Parts, and Workcenters
--
-- HOW TO EDIT (no deployment required):
--   gcloud storage cp reports/sql/quality_deviation_view.sql gs://voxdatalake-report-configs/sql/
--   The next pipeline run will recreate the view with the updated SQL.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- ORIGIN: built to attack the "NC-to-job correlation" gap flagged in
-- reports/quality_nonconformance.yaml and spreadsheets/mfg_job_schedule.md —
-- Quality_v_Problem has no Job_Key, so an NC alone can't say which job it
-- belongs to. Quality_v_Deviation DOES carry Job_Key, via the junction
-- tables Quality_v_Deviation_Job / _Problem / _Part / _Workcenter. See
-- catalog/plex_quality_views_catalog.md "Deviations" section for the full
-- schema discovery.
--
-- GRAIN: one row per Deviation record (Quality_v_Deviation.Deviation_No).
-- A single Deviation can touch multiple Jobs/Problems/Parts/Workcenters —
-- each is aggregated into a comma-separated list per deviation (via the CTEs
-- below) rather than fanning out rows, so one row stays one deviation.
--
-- UNCONFIRMED, DO NOT ASSUME: whether every logged Problem/NC gets a linked
-- Deviation, or only ones needing a documented/approved workaround.
-- "Deviation" in quality terminology classically means a planned, approved
-- exception to spec/process (see Approved_By/Effective_Date/Expiration_Date
-- below) — not necessarily every reactive nonconformance. Validate
-- problem_nos coverage against real Quality_v_Problem volume once live data
-- lands (data load begins 2026-08-24) before treating this as the complete
-- NC-to-job answer.
--
-- SAFE_CAST BOTH SIDES of every join key below, not just one. Confirmed
-- live 2026-08-19: Quality_v_Deviation and all 4 junction tables are
-- currently empty (pre-Monday data load), so BigQuery typed their _Key
-- columns as STRING; raw_Part_v_Job and raw_Quality_v_Problem are ALSO
-- currently empty for the same reason, while raw_Part_v_Part and
-- raw_Part_v_Workcenter already have live data (INT64 keys). Casting only
-- one side (matching most of this codebase's other views, which assume a
-- known-populated table on the far side) failed here with "No matching
-- signature for operator = for argument types: INT64, STRING" because
-- BOTH sides were STRING on job_links/problem_links. Double-casting is a
-- no-op once real data populates every table and fixes the type going in
-- either direction, so it's safe to leave this way permanently.

WITH

-- Job(s) this deviation applies to. raw_Part_v_Job is owned by the
-- work_orders pipeline (see reports/work_orders.yaml) — reused here as a
-- shared table, same rule as raw_Part_v_Part below.
job_links AS (
  SELECT
    dj.Deviation_Key,
    STRING_AGG(DISTINCT j.Job_No, ', ' ORDER BY j.Job_No)          AS job_nos
  FROM `{gcp_project}.{dataset}.raw_Quality_v_Deviation_Job` dj
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
    ON SAFE_CAST(dj.Job_Key AS INT64) = SAFE_CAST(j.Job_Key AS INT64)
  GROUP BY dj.Deviation_Key
),

-- Problem/NC record(s) this deviation was raised for.
problem_links AS (
  SELECT
    dp.Deviation_Key,
    STRING_AGG(DISTINCT q.Problem_No, ', ' ORDER BY q.Problem_No)  AS problem_nos
  FROM `{gcp_project}.{dataset}.raw_Quality_v_Deviation_Problem` dp
  LEFT JOIN `{gcp_project}.{dataset}.raw_Quality_v_Problem` q
    ON SAFE_CAST(dp.Problem_Key AS INT64) = SAFE_CAST(q.Problem_Key AS INT64)
  GROUP BY dp.Deviation_Key
),

-- Part(s) this deviation covers. raw_Part_v_Part is owned by the
-- sales_orders pipeline — same shared-table rule as work_orders_view.sql.
part_links AS (
  SELECT
    dpt.Deviation_Key,
    STRING_AGG(DISTINCT p.Part_No, ', ' ORDER BY p.Part_No)        AS part_nos
  FROM `{gcp_project}.{dataset}.raw_Quality_v_Deviation_Part` dpt
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
    ON SAFE_CAST(dpt.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)
  GROUP BY dpt.Deviation_Key
),

-- Workcenter(s) this deviation applies to. raw_Part_v_Workcenter is owned
-- by the work_orders pipeline — same shared-table rule as job_links above.
workcenter_links AS (
  SELECT
    dw.Deviation_Key,
    STRING_AGG(DISTINCT wc.Name, ', ' ORDER BY wc.Name)            AS workcenters
  FROM `{gcp_project}.{dataset}.raw_Quality_v_Deviation_Workcenter` dw
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
    ON SAFE_CAST(dw.Workcenter_Key AS INT64) = SAFE_CAST(wc.Workcenter_Key AS INT64)
  GROUP BY dw.Deviation_Key
)

SELECT

  -- ── Deviation identity ──────────────────────────────────────────────────
  d.Deviation_No                                  AS deviation_no,
  d.Code_No                                       AS code_no,

  -- Deviation_Type_Key / Deviation_Status_Key are real FKs (unlike
  -- Quality_v_Problem's inline Problem_Category/_Status text columns) —
  -- both lookup tables confirmed live, hence the joins below.
  dt.Deviation_Type                               AS deviation_type,
  ds.Deviation_Status                             AS deviation_status,
  SAFE_CAST(ds.Approved AS INT64)                 AS status_is_approved,
  SAFE_CAST(ds.Rejected AS INT64)                 AS status_is_rejected,
  SAFE_CAST(ds.Awaiting_Approval AS INT64)        AS status_is_awaiting_approval,

  -- ── What/why ────────────────────────────────────────────────────────────
  SAFE_CAST(d.Pieces_Affected AS FLOAT64)         AS pieces_affected,
  d.Reason                                        AS reason,
  d.Note                                          AS note,

  -- ── Correlated entities (see CTEs above) ───────────────────────────────
  jl.job_nos                                      AS job_nos,
  pl.problem_nos                                  AS problem_nos,
  pt.part_nos                                     AS part_nos,
  wl.workcenters                                  AS workcenters,

  -- ── Approval ────────────────────────────────────────────────────────────
  d.Approved_By                                   AS approved_by,

  -- DATE CONVERSION PATTERN: see reports/sql/work_orders_view.sql header —
  -- raw date columns can be INT64 nanoseconds, TIMESTAMP, or STRING.
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(d.Approved_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(d.Approved_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(d.Approved_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS approved_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(d.Effective_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(d.Effective_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(d.Effective_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS effective_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(d.Expiration_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(d.Expiration_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(d.Expiration_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS expiration_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(d.Add_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(d.Add_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(d.Add_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS add_date

FROM `{gcp_project}.{dataset}.raw_Quality_v_Deviation` d

LEFT JOIN `{gcp_project}.{dataset}.raw_Quality_v_Deviation_Type` dt
  ON SAFE_CAST(d.Deviation_Type_Key AS INT64) = SAFE_CAST(dt.Deviation_Type_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Quality_v_Deviation_Status` ds
  ON SAFE_CAST(d.Deviation_Status_Key AS INT64) = SAFE_CAST(ds.Deviation_Status_Key AS INT64)

LEFT JOIN job_links jl
  ON SAFE_CAST(d.Deviation_Key AS INT64) = SAFE_CAST(jl.Deviation_Key AS INT64)

LEFT JOIN problem_links pl
  ON SAFE_CAST(d.Deviation_Key AS INT64) = SAFE_CAST(pl.Deviation_Key AS INT64)

LEFT JOIN part_links pt
  ON SAFE_CAST(d.Deviation_Key AS INT64) = SAFE_CAST(pt.Deviation_Key AS INT64)

LEFT JOIN workcenter_links wl
  ON SAFE_CAST(d.Deviation_Key AS INT64) = SAFE_CAST(wl.Deviation_Key AS INT64)
