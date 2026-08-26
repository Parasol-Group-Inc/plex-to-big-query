-- mfg_job_schedule_success_metrics_report — MFG Job Schedule "Done YTD" /
-- "Done 2025" / "YTD List" / "2025 List" tabs, collapsed into one report
--
-- ORIGIN: those 4 sub-tabs are the same underlying calculated-metrics
-- concept split across 2 grains (Done YTD/Done 2025: full ~49-column detail;
-- YTD List/2025 List: a 7-column extract) and 2 time windows (current
-- year vs. prior-year archive). A spreadsheet needs that split to stay
-- readable; a BigQuery view doesn't — this is ONE continuous view over
-- every job regardless of date, so the "what's the exact archiving
-- boundary between Done YTD and Done 2025" open question
-- (spreadsheets/mfg_job_schedule_done_2025.md) doesn't apply to this build
-- at all. Filter by job_add_date/fg_testing_released_date at query time for
-- a "this year" vs "prior year" slice if that's ever needed.
--
-- GRAIN: one row per Job (not per job operation like mfg_job_schedule_report,
-- and NOT the finer "per blend/batch" grain the sheet's row-repeats-with-
-- different-Yield pattern implies — see spreadsheets/mfg_job_schedule_ytd_list.md
-- "Grain note". The real per-blend-batch source (Part_v_Job_Op_Batch) is
-- confirmed to exist but has 0 rows on every environment checked so far, so
-- per-blend granularity isn't buildable yet. This view aggregates to the
-- per-job level, which will UNDER-COUNT blend sub-batches once real data
-- lands on a job with more than one blend — revisit against
-- Part_v_Job_Op_Batch once it has real rows.
--
-- CONFIRMED FORMULAS (spreadsheets/mfg_job_schedule_done_ytd.md,
-- _ytd_list.md, _done_2025.md, _2025_list.md — reverse-engineered against
-- ~330 real spreadsheet rows across 3 tabs, zero contradictions):
--   Total Days   = FG Testing Released − Date Entered
--   TAT goal     = Total Days <= 84 (confirmed exact boundary: pass at 84,
--                  fail at 85 and 86, no exceptions)
--   Yield        = Caps Made / Capsule Count, goal 95% (stock) / 92% (custom)
--   Success Rating = (Yield gate + Deviation-is-NO gate + TAT gate) / 3
--   "Successful" (binary, for the Gate Stats rollup) = Success Rating = 100%
--     (all 3 gates), Emilio's call 2026-08-26 — not a lower partial-credit
--     threshold.
--
-- WHAT THIS BUILD CANNOT CONFIRM YET (Plex-side inputs, not formula gaps):
--   - "Date Entered" uses Part_v_Job.Add_Date as its Plex stand-in — same
--     already-flagged approximation as mfg_job_schedule_view.sql, not the
--     literal manually-typed "Date Entered" column.
--   - "FG Testing Released" uses the most recent APPROVED
--     Quality_v_Checksheet inspection date across all of a job's
--     operations. Quality_v_Checksheet_Status only has 4 generic flags
--     (Approved/Rejected/Awaiting_Approval/Expired) with no per-stage
--     label — there's no confirmed way yet to distinguish a "Raws
--     Released" checksheet from an "FG Testing Released" one. Taking the
--     LATEST approved checksheet is the closest available proxy (a job's
--     FG check should be its last one chronologically) but is unconfirmed.
--     Quality_v_Checksheet_Type.Description (not yet extracted) may carry
--     the real per-stage label — worth checking once real checksheet rows
--     exist to inspect.
--   - "Caps Made" (Yield's actual-output numerator) sums Part_v_Production
--     across ALL of a job's operations, not just Encapsulation specifically
--     — a deliberate generalization so Blending-only jobs (no encap step)
--     still get a Yield instead of a hard NULL, but Emilio's Q2
--     ("does the Yield formula hold for Blending-only jobs") is still
--     open and this hasn't been validated either way — no real production
--     data exists on any environment to check against yet.
--   - Deviation flag uses the Quality_v_Deviation_Job junction directly
--     (same source as quality_deviation_report) — still carries that
--     report's own "unconfirmed whether every Problem/NC gets a linked
--     Deviation" caveat (reports/quality_nonconformance.yaml).
--   - Stock-vs-Custom uses "job has a Job_Distribution row" (tied to a
--     customer order = Custom) as the primary signal, same unconfirmed
--     proxy already exposed on mfg_job_schedule_report.
--
-- is_rework (added per Emilio's 2026-08-26 call): never silently drops
-- rework rows from stats. Flags Job_Type = 'Rework' OR total_days < 0
-- (a negative Total Days is the confirmed rework/partial-batch signature —
-- see mfg_job_schedule_done_ytd.md) so any downstream consumer can filter
-- it out themselves; this view includes rework rows in every aggregate.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.

WITH

-- Actual production per job, summed across every operation on that job
-- (not just Encapsulation — see header). Non-rejected quantity only, same
-- Plex boolean convention (-1 = true) already confirmed on the 4 Daily
-- Reports.
job_production AS (
  SELECT
    SAFE_CAST(jo.Job_Key AS INT64)                                AS job_key,
    SUM(IF(COALESCE(SAFE_CAST(p.Rejected AS INT64), 0) = 0,
           SAFE_CAST(p.Quantity AS FLOAT64), 0))                   AS caps_made
  FROM `{gcp_project}.{dataset}.raw_Part_v_Production` p
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo
    ON SAFE_CAST(p.Job_Op_Key AS INT64) = SAFE_CAST(jo.Job_Op_Key AS INT64)
  GROUP BY job_key
),

-- Latest APPROVED checksheet inspection date per job, across all of that
-- job's operations — see header for why this is a proxy, not a confirmed
-- "FG Testing Released" match.
job_checksheet AS (
  SELECT
    SAFE_CAST(jo.Job_Key AS INT64) AS job_key,
    MAX(
      COALESCE(
        DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(cs.Inspection_Date AS STRING) AS INT64), 0), 1000))),
        NULLIF(SAFE_CAST(CAST(cs.Inspection_Date AS STRING) AS DATE), DATE '1970-01-01'),
        NULLIF(DATE(SAFE_CAST(CAST(cs.Inspection_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
      )
    ) AS fg_testing_released_date
  FROM `{gcp_project}.{dataset}.raw_Quality_v_Checksheet` cs
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo
    ON SAFE_CAST(cs.Job_Op_Key AS INT64) = SAFE_CAST(jo.Job_Op_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Quality_v_Checksheet_Status` cs_status
    ON SAFE_CAST(cs.Checksheet_Status_Key AS INT64) = SAFE_CAST(cs_status.Checksheet_Status_Key AS INT64)
  WHERE SAFE_CAST(cs_status.Approved AS INT64) = -1
  GROUP BY job_key
),

-- Same collapse pattern as mfg_job_schedule_view.sql: a job can have
-- multiple Job_Distribution rows (several releases) — collapsed to a
-- count so the main query's per-job grain doesn't fan out.
job_distribution_summary AS (
  SELECT
    SAFE_CAST(Job_Key AS INT64) AS job_key,
    COUNT(*)                    AS distribution_count
  FROM `{gcp_project}.{dataset}.raw_Part_v_Job_Distribution`
  GROUP BY job_key
),

-- Jobs with at least one linked Deviation, via the same junction table
-- quality_deviation_report is built from (reports/quality_nonconformance.yaml
-- pipeline — raw_Quality_v_Deviation_Job is a shared table, same rule as
-- raw_Part_v_Part elsewhere in this codebase).
deviation_jobs AS (
  SELECT DISTINCT SAFE_CAST(Job_Key AS INT64) AS job_key
  FROM `{gcp_project}.{dataset}.raw_Quality_v_Deviation_Job`
),

base AS (
  SELECT

    j.Job_No                                        AS job_no,
    p.Part_No                                       AS part_no,
    p.Name                                           AS part_name,

    jt.Job_Type                                     AS job_type,
    jds.distribution_count                          AS job_distribution_count,
    IF(COALESCE(jds.distribution_count, 0) > 0, 'Custom', 'Stock')
                                                     AS stock_or_custom,

    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(j.Add_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(j.Add_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(j.Add_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                               AS job_add_date,

    jc.fg_testing_released_date                     AS fg_testing_released_date,

    SAFE_CAST(j.Quantity AS FLOAT64)                AS capsule_count,
    jp.caps_made                                    AS caps_made,

    dj.job_key IS NOT NULL                          AS has_deviation

  FROM `{gcp_project}.{dataset}.raw_Part_v_Job` j

  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
    ON SAFE_CAST(j.Part_Key AS INT64) = p.Part_Key

  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Type` jt
    ON SAFE_CAST(j.Job_Type_Key AS INT64) = SAFE_CAST(jt.Job_Type_Key AS INT64)

  LEFT JOIN job_distribution_summary jds
    ON SAFE_CAST(j.Job_Key AS INT64) = jds.job_key

  LEFT JOIN job_production jp
    ON SAFE_CAST(j.Job_Key AS INT64) = jp.job_key

  LEFT JOIN job_checksheet jc
    ON SAFE_CAST(j.Job_Key AS INT64) = jc.job_key

  LEFT JOIN deviation_jobs dj
    ON SAFE_CAST(j.Job_Key AS INT64) = dj.job_key
),

metrics AS (
  SELECT
    base.*,

    DATE_DIFF(fg_testing_released_date, job_add_date, DAY)   AS total_days,

    SAFE_DIVIDE(caps_made, capsule_count)                     AS yield_pct,

    CASE
      WHEN SAFE_DIVIDE(caps_made, capsule_count) IS NULL THEN NULL
      WHEN stock_or_custom = 'Custom' THEN SAFE_DIVIDE(caps_made, capsule_count) >= 0.92
      ELSE SAFE_DIVIDE(caps_made, capsule_count) >= 0.95
    END                                                        AS yield_meets_goal,

    CASE
      WHEN DATE_DIFF(fg_testing_released_date, job_add_date, DAY) IS NULL THEN NULL
      ELSE DATE_DIFF(fg_testing_released_date, job_add_date, DAY) <= 84
    END                                                        AS tat_meets_goal,

    NOT has_deviation                                         AS deviation_gate_passed,

    (job_type = 'Rework') OR (DATE_DIFF(fg_testing_released_date, job_add_date, DAY) < 0)
                                                               AS is_rework,

    FORMAT_DATE('%Y-%m', fg_testing_released_date)             AS month

  FROM base
)

-- Success Rating = (gates passed) / 3, gates = Yield/Deviation/TAT — see
-- header. NULL gates (missing input, e.g. no production logged yet) count
-- as not-passed rather than being excluded from the denominator, so a job
-- with incomplete data reads as a low score instead of silently vanishing
-- from the average.
SELECT
  metrics.*,

  ( CAST(COALESCE(yield_meets_goal, FALSE) AS INT64)
  + CAST(COALESCE(deviation_gate_passed, FALSE) AS INT64)
  + CAST(COALESCE(tat_meets_goal, FALSE) AS INT64)
  ) / 3.0                                                     AS success_rating,

  COALESCE(yield_meets_goal, FALSE)
    AND COALESCE(deviation_gate_passed, FALSE)
    AND COALESCE(tat_meets_goal, FALSE)                        AS is_successful

FROM metrics
