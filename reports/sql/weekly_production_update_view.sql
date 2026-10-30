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
-- BOTTLING 9-PARTS ARE NOT PRODUCTION (Jennilyn, 2026-10-22): when Bottling
-- completes a job for a part starting with 9 (the finished-good version),
-- the same output was already counted on the job for its 5 part (the
-- bottled-bulk version). Counting both is double credit, so Bottling
-- records for 9-parts are dropped, good and scrap alike. Bottling only:
-- Labeling's output is all 9-parts and stays counted. Matched on the
-- part the production record itself names (Part_v_Production.Part_Key),
-- not the job's, so a record with no job is still judged.
-- BULK CASES STAY COUNTED (Jennilyn, 2026-10-22): 9xxxx-BK parts ("BULK
-- CASE", e.g. 93336-BKVOXNU-1) have no 5-part job, so they are exempt.
-- CUTOVER 2026-11-01 (Jennilyn, 2026-10-30): "we want to track
-- bottling/packaging totals for parts that start with 9 starting now." She
-- removed the 5-part BOM from those 9-parts so the output is no longer made
-- twice. The drop above applies only to records dated before 2026-11-01, so
-- October and earlier keep their numbers; from November 9-parts count. About
-- 14 in-use 9-parts still have a 5-part BOM; finishing that change is hers.
-- VISIBILITY, not a filter: bottling_9part_with_5_bom_qty is the 9-part
-- Bottling output whose part still has an active 5-part BOM line, i.e.
-- possible double credit. If it is not 0 from November, a BOM is unfinished.
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
    p.Part_Key,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(p.Record_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(p.Record_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(p.Record_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ) AS production_date
  FROM `{gcp_project}.{dataset}.raw_Part_v_Production` p
),

nine_with_five_bom AS (
  -- 9-parts that still have an active BOM line to a 5-part (see CUTOVER).
  SELECT DISTINCT SAFE_CAST(b.Part_Key AS INT64) AS part_key
  FROM `{gcp_project}.{dataset}.raw_Part_v_BOM` b
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` c
    ON SAFE_CAST(c.Part_Key AS INT64) = SAFE_CAST(b.Component_Part_Key AS INT64)
  WHERE STARTS_WITH(TRIM(c.Part_No), '5')
    AND COALESCE(SAFE_CAST(b.Active AS INT64), 1) != 0
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
       SAFE_CAST(prod.Quantity AS FLOAT64), 0)                       AS non_rejected_qty,
    -- For the CUTOVER visibility columns.
    (wc.Workcenter_Group = 'Bottling' AND (STARTS_WITH(COALESCE(TRIM(part.Part_No), ''), '9') AND NOT REGEXP_CONTAINS(COALESCE(TRIM(part.Part_No), ''), r'^9[0-9]{4}-BK')))
                                                                     AS is_bottling_9part,
    (f5.part_key IS NOT NULL)                                        AS has_5_bom

  FROM prod

  JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo
    ON SAFE_CAST(prod.Job_Op_Key AS INT64) = SAFE_CAST(jo.Job_Op_Key AS INT64)

  JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
    ON SAFE_CAST(jo.Workcenter_Key AS INT64) = wc.Workcenter_Key

  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` part
    ON SAFE_CAST(prod.Part_Key AS INT64) = SAFE_CAST(part.Part_Key AS INT64)

  LEFT JOIN nine_with_five_bom f5
    ON f5.part_key = SAFE_CAST(prod.Part_Key AS INT64)

  WHERE wc.Workcenter_Group IN ('Encapsulating', 'Bottling', 'Labeling', 'Printing')
    AND NOT (wc.Workcenter_Group = 'Bottling'
             AND STARTS_WITH(COALESCE(TRIM(part.Part_No), ''), '9')
             AND NOT REGEXP_CONTAINS(COALESCE(TRIM(part.Part_No), ''), r'^9[0-9]{4}-BK')
             AND prod.production_date < DATE '2026-11-01')
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
  ))                                                                   AS pct_of_month_complete,

  -- Added 2026-10-30 (CUTOVER above): MTD good Bottling output on 9-parts,
  -- and the part of it on 9-parts that still have a 5-part BOM line.
  SUM(IF(by_department.production_date >= bounds.month_start
         AND by_department.production_date <= bounds.today_date
         AND by_department.is_bottling_9part,
         by_department.non_rejected_qty, 0))                         AS mtd_bottling_9part_qty,
  SUM(IF(by_department.production_date >= bounds.month_start
         AND by_department.production_date <= bounds.today_date
         AND by_department.is_bottling_9part AND by_department.has_5_bom,
         by_department.non_rejected_qty, 0))                         AS mtd_bottling_9part_with_5_bom_qty

FROM departments
CROSS JOIN bounds
LEFT JOIN by_department
  ON by_department.department = departments.department

GROUP BY departments.department
ORDER BY departments.department
