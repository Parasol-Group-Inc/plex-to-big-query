-- quality_turnaround_time_report — Vox | Turn Around Time Report (best-
-- criteria NetSuite parity for BOTH "Turn Around Time Report - Last Month"
-- and "Turn Around Time Report - Rolling", mapping/netsuite-report-mapping.md
-- #69/#70 — nearest lead there was Plex's "Average Days to Problem
-- Resolution")
--
-- ⚠ READS Quality_v_Problem_2 (the UX table), NOT the classic
-- Quality_v_Problem — CHANGED 2026-09-22. The classic table is empty on this
-- tenant while the UI shows real records; see
-- quality_nonconformance_view.sql for the full finding.
--
-- THE CLOCK-START QUESTION IS NOW ANSWERABLE FROM DATA, AND BOTH ARE SHIPPED
-- ─────────────────────────────────────────────────────────────────────────
-- The long-standing open decision — does turnaround start at Problem_Date
-- (when it happened) or at the date it was written up? — stayed theoretical
-- while the table was empty. Problem_2 carries BOTH, both populated, and
-- they genuinely differ: Problem_Date is usually date-only (midnight),
-- Recorded_Date is a precise timestamp, verified across 22 live records on
-- 2026-09-22.
--
-- So this view no longer picks one and hides the other. `turnaround_days`
-- keeps its existing meaning (Problem_Date → Closed_Date) so nothing built
-- on it changes, and `turnaround_days_from_recorded` sits beside it. The gap
-- between them is reporting lag. If Vox's existing Performance/Bonus
-- standards were measured from the recorded date, the second column is the
-- comparable one — and the difference can be shown rather than argued about,
-- which was the whole point of the flag.
--
-- Only closed problems have a turnaround value — open problems (Closed_Date
-- IS NULL) are still included with NULL so the report can show open-vs-
-- closed counts, but excluded from any average.
--
-- ⚠ CLOSED DATES ARE BEING SET IN THE FUTURE on this tenant: of the 2 records
-- with a Closed_Date on 2026-09-22, one is dated 2026-09-23 and the other
-- 2026-09-25 while still sitting in "Submitted for Closure". A negative or
-- implausible turnaround is therefore a DATA ENTRY question for Quality, not
-- an arithmetic bug here. `closed_date_in_future` flags them rather than
-- quietly dropping them.
--
-- "Rolling" vs. "Last Month": both readings are just different WINDOWS over
-- the same per-record columns below — no window is hardcoded here. Filter
-- closed_month to one calendar month for "Last Month", or filter closed_date
-- within a trailing N-day window for "Rolling", at the consuming layer.
--
-- Not re-extracted — bq_view entry in reports/quality_nonconformance.yaml,
-- same raw_Quality_v_Problem_2 table as quality_nonconformance_report.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per Quality_v_Problem_2 record.

WITH base AS (
  SELECT
    q.Problem_No                                        AS problem_no,
    f.Name                                              AS problem_form,
    q.Problem_Type                                      AS problem_type,
    q.Problem_Category                                  AS problem_category,
    q.Problem_Status                                    AS problem_status,

    -- DATE CONVERSION PATTERN: see reports/sql/work_orders_view.sql header.
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                                   AS opened_date,

    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Recorded_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(q.Recorded_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(q.Recorded_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                                   AS recorded_date,

    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                                   AS closed_date,

    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Problem_Due_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(q.Problem_Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(q.Problem_Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                                   AS due_date

  FROM `{gcp_project}.{dataset}.raw_Quality_v_Problem_2` q
  LEFT JOIN `{gcp_project}.{dataset}.raw_Quality_v_Problem_Form` f
    ON SAFE_CAST(q.Problem_Form_Key AS INT64) = SAFE_CAST(f.Problem_Form_Key AS INT64)
)

SELECT
  problem_no,
  problem_form,
  problem_type,
  problem_category,
  problem_status,

  opened_date,
  recorded_date,
  closed_date,
  due_date,

  -- The clock as originally built: when the problem happened → closed.
  DATE_DIFF(closed_date, opened_date, DAY)              AS turnaround_days,

  -- The same clock started when the problem was written up. The gap between
  -- the two is reporting lag.
  DATE_DIFF(closed_date, recorded_date, DAY)            AS turnaround_days_from_recorded,

  DATE_DIFF(recorded_date, opened_date, DAY)            AS reporting_lag_days,

  -- On-time closure against Quality's own due date — a metric the classic
  -- table could not support, because it had no due date.
  CASE
    WHEN closed_date IS NULL OR due_date IS NULL THEN NULL
    ELSE closed_date <= due_date
  END                                                   AS closed_on_time,

  closed_date > CURRENT_DATE()                          AS closed_date_in_future,

  DATE_TRUNC(closed_date, MONTH)                        AS closed_month

FROM base
ORDER BY closed_date DESC NULLS LAST, problem_no DESC
