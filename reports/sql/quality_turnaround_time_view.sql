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
-- THE STANDARDS ARE NOW JOINED IN — from a hand-maintained table
-- ─────────────────────────────────────────────────────────────────────────
-- `{dataset}.turnaround_standards` holds the Performance and Bonus day counts
-- per stock type, in WORK days — compared against turnaround_work_days (see
-- the `wd` CTE below; calendar days were compared until 2026-09-24). It is **hand-maintained by Jennilyn directly in BigQuery**:
-- not written by the ETL, not managed by Terraform, and deliberately not fed
-- by the manual-data web app — that tab was dropped on 2026-09-21 because
-- these change about never, and a form is for numbers that change often.
-- Rebuild DDL and how to edit it: docs/reports/turnaround_standards.md.
--
-- ⚠ THE TABLE MUST EXIST OR THIS VIEW FAILS TO CREATE, exactly like
-- scorecard_goals does for the three vs-goal views — and it fails looking
-- like a broken report rather than a missing dependency. An EMPTY table is
-- fine: every standard column reads NULL and `standard_source` says
-- 'none set'.
--
-- MATCHING IS AN EXACT STRING MATCH on Plex's `Part_Type` (Components, Raw
-- Materials, Semi-Finished Goods, Finished Goods, WIP, Supply, Inspection),
-- with the same failure mode as the scorecard's goal `scope`: a typo yields a
-- NULL standard, not an error. Two deliberate safety valves, because 12 of 22
-- live NC records have no part at all and therefore no stock type:
--   1. a row with a BLANK (or 'ALL') stock_type is the catch-all, used when
--      the part type has no row of its own or there is no part;
--   2. `standard_source` says which of the two was used, so a catch-all
--      number is never mistaken for a type-specific one.
--
-- ⚠ "Item Stock Type" on the Monthly TAT Analysis sheet is ASSUMED to mean
-- Plex's Part_Type. That is the closest thing on the part master — there is
-- no column called Stock_Type — but nobody has confirmed it against the
-- sheet. If it turns out to mean something else, only the join column here
-- and the values in the table change; the shape does not.
--
-- Not re-extracted — bq_view entry in reports/quality_nonconformance.yaml,
-- same raw_Quality_v_Problem_2 table as quality_nonconformance_report.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per Quality_v_Problem_2 record.

WITH dated AS (
  SELECT
    q.Problem_No                                        AS problem_no,
    f.Name                                              AS problem_form,
    q.Problem_Type                                      AS problem_type,
    q.Problem_Category                                  AS problem_category,
    q.Problem_Status                                    AS problem_status,
    pt.Part_No                                          AS part_no,
    pt.Part_Type                                        AS stock_type,

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
  -- Part_Key is -1 on a record with no part; the join simply finds nothing.
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` pt
    ON SAFE_CAST(q.Part_Key AS INT64) = SAFE_CAST(pt.Part_Key AS INT64)
),

-- WORK DAYS — ADDED 2026-09-24. The Performance/Bonus standards are WORK
-- days (the old TAT sheets say so), but DATE_DIFF(..., DAY) counts calendar
-- days, so a record closed in 8 work days read as 10-12 and was marked as
-- missing a 10-day standard it had met. Each date gets a running weekday
-- index here, and the work-day turnaround is simply the difference.
--
-- The index counts Mon–Fri days from Monday 1900-01-01 up to and INCLUDING
-- the date: 5 per full week plus the weekdays in the part week. Subtracting
-- two of them therefore counts the work days AFTER the start date up to and
-- including the close date — the same "start day excluded" convention as
-- DATE_DIFF, so a same-day close is 0 either way, Friday → Monday is 1, and a
-- close dated before its open comes out negative rather than silently 0.
--
-- ⚠ Mon–Fri ONLY — NO HOLIDAYS. No holiday calendar is extracted from Plex or
-- kept anywhere in this project, so a record open over Thanksgiving counts
-- that day as a work day. If Quality's sheets excluded holidays, a holiday
-- table joined here is the fix; the shape of the columns would not change.
wd AS (
  SELECT
    *,
    5 * DIV(DATE_DIFF(opened_date,   DATE '1900-01-01', DAY) + 1, 7)
      + LEAST(MOD(DATE_DIFF(opened_date,   DATE '1900-01-01', DAY) + 1, 7), 5) AS opened_wd_idx,
    5 * DIV(DATE_DIFF(recorded_date, DATE '1900-01-01', DAY) + 1, 7)
      + LEAST(MOD(DATE_DIFF(recorded_date, DATE '1900-01-01', DAY) + 1, 7), 5) AS recorded_wd_idx,
    5 * DIV(DATE_DIFF(closed_date,   DATE '1900-01-01', DAY) + 1, 7)
      + LEAST(MOD(DATE_DIFF(closed_date,   DATE '1900-01-01', DAY) + 1, 7), 5) AS closed_wd_idx
  FROM dated
),

-- The day counts live one layer up from the dates they are built on: a SELECT
-- alias cannot be referenced by a sibling item in the same SELECT, and
-- repeating the date-conversion COALESCE four more times would be worse.
base AS (
  SELECT
    * EXCEPT (opened_wd_idx, recorded_wd_idx, closed_wd_idx),
    -- CALENDAR days, kept exactly as before so nothing built on them moves.
    -- The clock as originally built: when the problem happened → closed.
    DATE_DIFF(closed_date, opened_date, DAY)            AS turnaround_days,
    -- The same clock started when the problem was written up. The gap
    -- between the two is reporting lag.
    DATE_DIFF(closed_date, recorded_date, DAY)          AS turnaround_days_from_recorded,
    DATE_DIFF(recorded_date, opened_date, DAY)          AS reporting_lag_days,
    -- WORK days (Mon–Fri) for both clocks — what the standards are written
    -- in, and what met_performance_standard / met_bonus_standard use.
    closed_wd_idx - opened_wd_idx                       AS turnaround_work_days,
    closed_wd_idx - recorded_wd_idx                     AS turnaround_work_days_from_recorded
  FROM wd
),

-- A change to a standard is made by ADDING a row, so history stays intact.
-- Which row applies therefore depends on WHEN the problem happened, not on
-- which row is newest overall: a standard that takes effect in December must
-- not be applied to a September problem. Both lookups below pick the newest
-- row effective on or before each record's own month.
standards AS (
  SELECT
    UPPER(TRIM(IFNULL(stock_type, '')))                 AS stock_type_key,
    effective_month,
    performance_days,
    bonus_days
  FROM `{gcp_project}.{dataset}.turnaround_standards`
  WHERE effective_month IS NOT NULL
),

-- The standard for each record's own stock type, as at its month.
by_type AS (
  SELECT
    b.problem_no,
    ARRAY_AGG(STRUCT(s.performance_days, s.bonus_days)
              ORDER BY s.effective_month DESC LIMIT 1)[OFFSET(0)] AS std
  FROM base b
  JOIN standards s
    ON s.stock_type_key = UPPER(TRIM(IFNULL(b.stock_type, '')))
   AND s.stock_type_key NOT IN ('', 'ALL')
   AND s.effective_month <= DATE_TRUNC(b.opened_date, MONTH)
  GROUP BY b.problem_no
),

-- The catch-all, for a record with no part or a stock type nobody listed.
-- 12 of 22 live NC records have no part at all, so this is the common path
-- rather than an edge case.
catch_all AS (
  SELECT
    b.problem_no,
    ARRAY_AGG(STRUCT(s.performance_days, s.bonus_days)
              ORDER BY s.effective_month DESC LIMIT 1)[OFFSET(0)] AS std
  FROM base b
  JOIN standards s
    ON s.stock_type_key IN ('', 'ALL')
   AND s.effective_month <= DATE_TRUNC(b.opened_date, MONTH)
  GROUP BY b.problem_no
)

SELECT
  b.problem_no,
  b.problem_form,
  b.problem_type,
  b.problem_category,
  b.problem_status,

  b.opened_date,
  b.recorded_date,
  b.closed_date,
  b.due_date,

  b.turnaround_days,
  b.turnaround_days_from_recorded,
  b.reporting_lag_days,
  b.turnaround_work_days,
  b.turnaround_work_days_from_recorded,

  -- On-time closure against Quality's own due date — a metric the classic
  -- table could not support, because it had no due date.
  CASE
    WHEN b.closed_date IS NULL OR b.due_date IS NULL THEN NULL
    ELSE b.closed_date <= b.due_date
  END                                                   AS closed_on_time,

  b.closed_date > CURRENT_DATE()                          AS closed_date_in_future,

  DATE_TRUNC(b.closed_date, MONTH)                        AS closed_month,

  -- ── The standards, and whether this record met them ──────────────────
  b.stock_type,
  COALESCE(t.std.performance_days, c.std.performance_days) AS performance_standard_days,
  COALESCE(t.std.bonus_days,       c.std.bonus_days)       AS bonus_standard_days,

  -- Which standard was used. A catch-all figure must never be mistaken for a
  -- type-specific one, and 'none set' must never be mistaken for a zero.
  CASE
    WHEN t.std.performance_days IS NOT NULL THEN 'stock type'
    WHEN c.std.performance_days IS NOT NULL THEN 'catch-all'
    ELSE 'none set'
  END                                                   AS standard_source,

  -- NULL rather than FALSE when the record is open or no standard exists —
  -- "we do not know yet" and "missed it" are different answers.
  --
  -- Measured in WORK days since 2026-09-24 (they compared calendar days to a
  -- work-day standard before), on the original Problem_Date clock — which
  -- clock the standards mean is still Quality's call; see the header.
  CASE
    WHEN b.turnaround_work_days IS NULL THEN NULL
    WHEN COALESCE(t.std.performance_days, c.std.performance_days) IS NULL THEN NULL
    ELSE b.turnaround_work_days <= COALESCE(t.std.performance_days, c.std.performance_days)
  END                                                   AS met_performance_standard,
  CASE
    WHEN b.turnaround_work_days IS NULL THEN NULL
    WHEN COALESCE(t.std.bonus_days, c.std.bonus_days) IS NULL THEN NULL
    ELSE b.turnaround_work_days <= COALESCE(t.std.bonus_days, c.std.bonus_days)
  END                                                   AS met_bonus_standard

FROM base b
LEFT JOIN by_type   t ON t.problem_no = b.problem_no
LEFT JOIN catch_all c ON c.problem_no = b.problem_no

ORDER BY b.closed_date DESC NULLS LAST, problem_no DESC
