-- weekly_production_update_report — "Weekly Production Update" Google Sheet,
-- Goals tab (partial build)
--
-- ORIGIN: spreadsheets/weekly_production_update.md. Covers the Actual
-- WTD/MTD quantity columns for 4 departments (Encap, Bottling, Labeling,
-- Printing) plus "% of Month Complete" — the only columns with a confirmed
-- Plex source or no data dependency at all.
--
-- NOT BUILT (Emilio's calls 2026-08-26, see the doc above):
--   - Goal / % of Goal — no Plex source exists for the goal figures at all
--     (business-set targets). Decided to keep these manual in the sheet
--     rather than stand up a reference table this pipeline reads.
--   - Weekly/Monthly Capacity Avg % (the "Capacity" tab) — no confirmed
--     formula or theoretical-capacity input; left genuinely open.
--   - Weekly Loss (Encap) "Time (hours)" — no confirmed Plex source for
--     lost time, only for lost quantity (Rejected flag, same as the
--     existing Daily Reports' scrap_qty — not built here as a separate
--     column since it isn't part of this tab's Actual/Goal table).
--
-- SAME SOURCE/CONVENTION AS THE 4 DAILY REPORTS (encap/blending/labeling/
-- packaging_daily_report_view.sql): Part_v_Production.Quantity, filtered to
-- non-rejected (Plex represents boolean true as -1, not 1), joined through
-- Part_v_Job_Op to Part_v_Workcenter.Workcenter_Group. Only difference:
-- summed over a rolling week/month window instead of grouped by single day,
-- and covers Printing for the first time (no existing Daily Report does).
--
-- DEPARTMENT MAPPING: this sheet's "Bottling" and "Printing" match their
-- own Workcenter_Group names directly (both confirmed live, see
-- reports-list/production.md's 2026-08-21 confirmed-workcenter-roster
-- note) — no relabeling needed, unlike packaging_daily_report_view.sql
-- (whose sheet says "Packaging" but the real Plex group is "Bottling").
-- This sheet has no Blending row at all, unlike the 4 Daily Reports.
--
-- WTD WINDOW (Emilio's call 2026-08-26): "WTD (M-T)" = Monday of the
-- current week through today, standard week-to-date — not literally
-- Monday-through-Thursday. MTD = 1st of the current month through today.
-- Both computed in America/Denver (Mountain), matching this pipeline's
-- own scheduling convention, since Plex production dates have no
-- explicit timezone conversion applied elsewhere in this codebase either.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per department.

WITH

today AS (
  SELECT CURRENT_DATE('America/Denver') AS today_date
),

bounds AS (
  SELECT
    today_date,
    DATE_TRUNC(today_date, WEEK(MONDAY))  AS week_start,
    DATE_TRUNC(today_date, MONTH)          AS month_start
  FROM today
),

prod AS (
  SELECT
    p.Quantity,
    p.Rejected,
    p.Job_Op_Key,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(p.Record_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(p.Record_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(p.Record_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ) AS production_date
  FROM `{gcp_project}.{dataset}.raw_Part_v_Production` p
),

by_department AS (
  SELECT
    -- Map Plex's Workcenter_Group name to this sheet's own department
    -- label (only Encapsulating -> Encap differs; Bottling/Labeling/
    -- Printing already match their Workcenter_Group verbatim).
    CASE wc.Workcenter_Group
      WHEN 'Encapsulating' THEN 'Encap'
      ELSE wc.Workcenter_Group
    END                                                             AS department,
    prod.production_date,
    -- Plex represents boolean true as -1, not 1 (confirmed live, same
    -- convention as encap_daily_report_view.sql and friends).
    IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0,
       SAFE_CAST(prod.Quantity AS FLOAT64), 0)                       AS non_rejected_qty

  FROM prod

  JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo
    ON SAFE_CAST(prod.Job_Op_Key AS INT64) = SAFE_CAST(jo.Job_Op_Key AS INT64)

  JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
    ON SAFE_CAST(jo.Workcenter_Key AS INT64) = wc.Workcenter_Key

  WHERE wc.Workcenter_Group IN ('Encapsulating', 'Bottling', 'Labeling', 'Printing')
),

-- Fixed department roster so a department with zero production in the
-- window still gets a row (0, not missing) rather than silently
-- disappearing from the report, matching the sheet's own fixed 4 rows.
departments AS (
  SELECT department
  FROM UNNEST(['Encap', 'Bottling', 'Labeling', 'Printing']) AS department
)

SELECT
  departments.department,

  SUM(IF(by_department.production_date >= bounds.week_start
         AND by_department.production_date <= bounds.today_date,
         by_department.non_rejected_qty, 0))                         AS wtd_actual_qty,

  SUM(IF(by_department.production_date >= bounds.month_start
         AND by_department.production_date <= bounds.today_date,
         by_department.non_rejected_qty, 0))                         AS mtd_actual_qty,

  ANY_VALUE(SAFE_DIVIDE(
    EXTRACT(DAY FROM bounds.today_date),
    EXTRACT(DAY FROM LAST_DAY(bounds.today_date))
  ))                                                                   AS pct_of_month_complete

FROM departments
CROSS JOIN bounds
LEFT JOIN by_department
  ON by_department.department = departments.department

GROUP BY departments.department
ORDER BY departments.department
