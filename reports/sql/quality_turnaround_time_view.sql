-- quality_turnaround_time_report — Vox | Turn Around Time Report (best-
-- criteria NetSuite parity for BOTH "Turn Around Time Report - Last Month"
-- and "Turn Around Time Report - Rolling", mapping/netsuite-report-mapping.md
-- #69/#70 — nearest lead there was Plex's "Average Days to Problem
-- Resolution")
--
-- BEST-CRITERIA ASSUMPTION, NOT NETSUITE-CONFIRMED: TAT is computed as
-- Closed_Date - Problem_Date (days) per Quality_v_Problem record. This
-- assumes Problem_Date is the correct "opened" timestamp for a turn-around
-- clock — Quality_v_Problem also has Entered_Date and Response_Due_Date,
-- either of which could be the intended start point instead. Flag for
-- data-scientist review: confirm Problem_Date vs. Entered_Date as the TAT
-- start, and whether "Turn Around Time" here means problem-resolution time
-- specifically (this report's scope) or something broader (e.g. supplier
-- return turnaround, a different Plex concept entirely).
--
-- Only closed problems have a turnaround_days value — open problems
-- (Closed_Date IS NULL) are still included with turnaround_days = NULL so
-- the report can show open-vs-closed counts, but excluded from any average.
--
-- "Rolling" vs. "Last Month": both readings are just different WINDOWS over
-- the same per-record turnaround_days + closed_month columns below — no
-- window is hardcoded here. Filter turnaround_month to one calendar month
-- for "Last Month", or filter closed_date within a trailing N-day window
-- for "Rolling", at the consuming dashboard/query layer.
--
-- Not re-extracted — bq_view entry in reports/quality_nonconformance.yaml,
-- same raw_Quality_v_Problem table as quality_nonconformance_report.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per Quality_v_Problem record.

SELECT

  q.Problem_No                                          AS problem_no,
  q.Problem_Type                                        AS problem_type,
  q.Problem_Category                                    AS problem_category,
  q.Problem_Status                                       AS problem_status,

  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS opened_date,

  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS closed_date,

  DATE_DIFF(
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ),
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ),
    DAY
  )                                                     AS turnaround_days,

  DATE_TRUNC(
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ),
    MONTH
  )                                                     AS closed_month

FROM `{gcp_project}.{dataset}.raw_Quality_v_Problem` q
