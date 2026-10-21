-- quality_turnaround_time_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/quality_turnaround_time_view.sql
-- confidence: low
-- plex_views: Quality_v_Problem_2, Quality_v_Problem_Form, Part_v_Part
-- notes: turnaround_standards is a hand-maintained BigQuery table with no Plex equivalent; replaced by an empty placeholder CTE, so every standard column is NULL and standard_source = 'none set' until real rows are pasted in.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per Quality_v_Problem_2 record.
-- RULE: turnaround_days = Problem_Date -> Closed_Date (calendar); *_from_recorded starts at Recorded_Date instead.
-- RULE: work days are Mon-Fri only, no holidays; standards are compared against work days.
-- RULE: a standard row is picked per record by stock type (Part_Type), else the blank/ALL catch-all,
--       taking the newest effective_month on or before the record's opened month.
WITH dated AS (
  SELECT
    q.Problem_No                        AS problem_no,
    f.Name                              AS problem_form,
    q.Problem_Type                      AS problem_type,
    q.Problem_Category                  AS problem_category,
    q.Problem_Status                    AS problem_status,
    pt.Part_No                          AS part_no,
    pt.Part_Type                        AS stock_type,
    CAST(q.Problem_Date AS date)        AS opened_date,
    CAST(q.Recorded_Date AS date)       AS recorded_date,
    CAST(q.Closed_Date AS date)         AS closed_date,
    CAST(q.Problem_Due_Date AS date)    AS due_date
  FROM Quality_v_Problem_2 AS q
  LEFT JOIN Quality_v_Problem_Form AS f
    ON q.Problem_Form_Key = f.Problem_Form_Key
  LEFT JOIN Part_v_Part AS pt                -- Part_Key is -1 on a record with no part
    ON q.Part_Key = pt.Part_Key
),

-- running Mon-Fri index from Monday 1900-01-01, counting up to and including the date
wd AS (
  SELECT
    d.*,
    5 * ((DATEDIFF(day, '19000101', d.opened_date)   + 1) / 7)
      + CASE WHEN ((DATEDIFF(day, '19000101', d.opened_date)   + 1) % 7) < 5
             THEN ((DATEDIFF(day, '19000101', d.opened_date)   + 1) % 7) ELSE 5 END AS opened_wd_idx,
    5 * ((DATEDIFF(day, '19000101', d.recorded_date) + 1) / 7)
      + CASE WHEN ((DATEDIFF(day, '19000101', d.recorded_date) + 1) % 7) < 5
             THEN ((DATEDIFF(day, '19000101', d.recorded_date) + 1) % 7) ELSE 5 END AS recorded_wd_idx,
    5 * ((DATEDIFF(day, '19000101', d.closed_date)   + 1) / 7)
      + CASE WHEN ((DATEDIFF(day, '19000101', d.closed_date)   + 1) % 7) < 5
             THEN ((DATEDIFF(day, '19000101', d.closed_date)   + 1) % 7) ELSE 5 END AS closed_wd_idx
  FROM dated AS d
),

base AS (
  SELECT
    w.problem_no, w.problem_form, w.problem_type, w.problem_category, w.problem_status,
    w.part_no, w.stock_type, w.opened_date, w.recorded_date, w.closed_date, w.due_date,
    DATEDIFF(day, w.opened_date, w.closed_date)         AS turnaround_days,
    DATEDIFF(day, w.recorded_date, w.closed_date)       AS turnaround_days_from_recorded,
    DATEDIFF(day, w.opened_date, w.recorded_date)       AS reporting_lag_days,
    w.closed_wd_idx - w.opened_wd_idx                   AS turnaround_work_days,
    w.closed_wd_idx - w.recorded_wd_idx                 AS turnaround_work_days_from_recorded
  FROM wd AS w
),

-- PLACEHOLDER, NOT FROM PLEX: turnaround_standards is typed by hand in BigQuery
-- (Performance/Bonus work-day standards per Part_Type). Empty here, so no standard applies.
-- To test with real numbers, replace with e.g.:
--   SELECT * FROM (VALUES ('', CAST('2026-01-01' AS date), 10, 5)) AS v(stock_type, effective_month, performance_days, bonus_days)
turnaround_standards AS (
  SELECT
    CAST(NULL AS varchar(100)) AS stock_type,
    CAST(NULL AS date)         AS effective_month,
    CAST(NULL AS int)          AS performance_days,
    CAST(NULL AS int)          AS bonus_days
  WHERE 1 = 0
),

standards AS (
  SELECT
    UPPER(LTRIM(RTRIM(ISNULL(ts.stock_type, '')))) AS stock_type_key,
    ts.effective_month,
    ts.performance_days,
    ts.bonus_days
  FROM turnaround_standards AS ts
  WHERE ts.effective_month IS NOT NULL
),

-- standard for the record's own stock type, newest effective on or before its month
by_type_ranked AS (
  SELECT
    b.problem_no, s.performance_days, s.bonus_days,
    ROW_NUMBER() OVER (PARTITION BY b.problem_no ORDER BY s.effective_month DESC) AS rn
  FROM base AS b
  JOIN standards AS s
    ON s.stock_type_key = UPPER(LTRIM(RTRIM(ISNULL(b.stock_type, ''))))
   AND s.stock_type_key NOT IN ('', 'ALL')
   AND s.effective_month <= DATEFROMPARTS(YEAR(b.opened_date), MONTH(b.opened_date), 1)
),

by_type AS (
  SELECT r.problem_no, r.performance_days, r.bonus_days
  FROM by_type_ranked AS r
  WHERE r.rn = 1
),

-- catch-all (blank or ALL stock type), for records with no part or an unlisted type
catch_all_ranked AS (
  SELECT
    b.problem_no, s.performance_days, s.bonus_days,
    ROW_NUMBER() OVER (PARTITION BY b.problem_no ORDER BY s.effective_month DESC) AS rn
  FROM base AS b
  JOIN standards AS s
    ON s.stock_type_key IN ('', 'ALL')
   AND s.effective_month <= DATEFROMPARTS(YEAR(b.opened_date), MONTH(b.opened_date), 1)
),

catch_all AS (
  SELECT r.problem_no, r.performance_days, r.bonus_days
  FROM catch_all_ranked AS r
  WHERE r.rn = 1
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
  CASE
    WHEN b.closed_date IS NULL OR b.due_date IS NULL THEN NULL
    WHEN b.closed_date <= b.due_date THEN 1 ELSE 0
  END                                                   AS closed_on_time,
  CASE
    WHEN b.closed_date IS NULL THEN NULL
    WHEN b.closed_date > CAST(GETDATE() AS date) THEN 1 ELSE 0
  END                                                   AS closed_date_in_future,
  DATEFROMPARTS(YEAR(b.closed_date), MONTH(b.closed_date), 1) AS closed_month,
  b.stock_type,
  COALESCE(t.performance_days, c.performance_days)      AS performance_standard_days,
  COALESCE(t.bonus_days, c.bonus_days)                  AS bonus_standard_days,
  CASE
    WHEN t.performance_days IS NOT NULL THEN 'stock type'
    WHEN c.performance_days IS NOT NULL THEN 'catch-all'
    ELSE 'none set'
  END                                                   AS standard_source,
  -- NULL (not 0) when the record is open or no standard exists; measured in work days on the Problem_Date clock
  CASE
    WHEN b.turnaround_work_days IS NULL THEN NULL
    WHEN COALESCE(t.performance_days, c.performance_days) IS NULL THEN NULL
    WHEN b.turnaround_work_days <= COALESCE(t.performance_days, c.performance_days) THEN 1 ELSE 0
  END                                                   AS met_performance_standard,
  CASE
    WHEN b.turnaround_work_days IS NULL THEN NULL
    WHEN COALESCE(t.bonus_days, c.bonus_days) IS NULL THEN NULL
    WHEN b.turnaround_work_days <= COALESCE(t.bonus_days, c.bonus_days) THEN 1 ELSE 0
  END                                                   AS met_bonus_standard
FROM base AS b
LEFT JOIN by_type AS t
  ON t.problem_no = b.problem_no
LEFT JOIN catch_all AS c
  ON c.problem_no = b.problem_no
ORDER BY CASE WHEN b.closed_date IS NULL THEN 1 ELSE 0 END, b.closed_date DESC, b.problem_no DESC;
