-- production_monthly_by_workcenter_group_report — actual production quantity
-- and scrap per work center group per month, across every group at once
-- (Plex-native "Actual" half of the Vox Nutrition Scorecard's Production
-- Actual-vs-Goal tiles — Encapsulation, Bottling, Labeling and any other
-- group Vox adds later. See
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-04, per the Emilio/Jennilyn meeting (meetings-reference/Sep-1/).
-- Asked for in exactly these terms:
--   "Yeah, so we'll have to set up the goal table, and then these are the
--    production by work center group by month."
--
-- WHY THIS EXISTS WHEN THE 4 DAILY REPORTS ALREADY DO: encap_daily_report,
-- blending_daily_report, labeling_daily_report and packaging_daily_report
-- are per-DAY, per-WORKCENTER, and each one hardcodes a single
-- Workcenter_Group filter. The scorecard tile is per-MONTH, per-GROUP, and
-- needs every group in one place to sit against one goal table. Rolling the
-- four daily views up in Looker Studio would silently miss any group that
-- doesn't have its own daily report, and would need a new view every time
-- Vox adds a line. This reads Part_v_Production directly and groups itself,
-- so a new work center group appears automatically.
--
-- SAME SOURCE, SAME BUG-FIX AS THE DAILY REPORTS: built on
-- Part_v_Production (Record_Date / Workcenter_Key / Quantity / Rejected),
-- the table the daily reports were corrected onto 2026-08-21 after a live
-- screenshot of Plex's own "Job Production" report confirmed it — not
-- Part_v_Cell_Production, which has no Rejected column at all.
--
-- NO Job_Op JOIN — DELIBERATE: the daily reports had to LEFT JOIN
-- Part_v_Job_Op to reach Job/Part, and that join silently dropped every row
-- whose operation had since closed (fixed 2026-09-01, see
-- encap_daily_report_view.sql's header for the full story). This view needs
-- neither Job nor Part, so it doesn't join Job_Op at all and is structurally
-- immune to that whole class of bug. Workcenter_Key is on Part_v_Production
-- directly.
--
-- BOOLEAN CONVENTION: Part_v_Production.Rejected is 1 on a rejected record
-- (checked 2026-09-24 against the only real one, Bottling Line 1, 500 units).
-- It used to be tested as -1 on a family "convention" the container flags
-- had already disproved, which counted no scrap at all. Scrap is now
-- `!= 0`, which holds whichever value Plex uses. Check real rows, never
-- the family (docs/CHEATSHEET.md, Booleans).
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
-- Not re-extracted — bq_view entry in reports/work_orders.yaml, same raw
-- tables the 4 daily reports already use.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (production month, work center group).

WITH prod AS (
  SELECT
    p.Quantity,
    p.Rejected,
    p.Workcenter_Key,
    p.Part_Key,
    -- DATE CONVERSION PATTERN: raw date columns arrive as INT64 nanoseconds,
    -- TIMESTAMP, or STRING depending on how the table was loaded. Every
    -- branch routes through CAST(col AS STRING) first because that cast is
    -- legal from ANY type — a direct SAFE_CAST(INT64 AS DATE) is an invalid
    -- cast pair and fails at view-creation time. 1970-01-01 = epoch sentinel.
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
)

SELECT

  DATE_TRUNC(prod.production_date, MONTH)               AS production_month,
  wc.Workcenter_Group                                   AS workcenter_group,

  COUNT(DISTINCT prod.production_date)                  AS days_with_production,
  COUNT(DISTINCT wc.Workcenter_Key)                     AS workcenters_active,

  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0,
         SAFE_CAST(prod.Quantity AS FLOAT64), 0))       AS actual_qty,
  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) != 0,
         SAFE_CAST(prod.Quantity AS FLOAT64), 0))       AS scrap_qty,
  SUM(SAFE_CAST(prod.Quantity AS FLOAT64))              AS total_qty,

  -- Scrap rate as a share of everything run, good and bad. Complements the
  -- FPY figure in quality_fpy_by_area_month_report, which is computed on the
  -- same table at the same grain and should agree with this.
  SAFE_DIVIDE(
    SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) != 0,
           SAFE_CAST(prod.Quantity AS FLOAT64), 0)),
    NULLIF(SUM(SAFE_CAST(prod.Quantity AS FLOAT64)), 0)
  )                                                     AS scrap_rate,

  -- Added 2026-10-30 (CUTOVER above): good Bottling output on 9-parts (bulk
  -- cases excluded), and the part of it on 9-parts that still have a 5-part
  -- BOM line. Both 0 before November and outside Bottling.
  SUM(IF(wc.Workcenter_Group = 'Bottling' AND (STARTS_WITH(COALESCE(TRIM(part.Part_No), ''), '9') AND NOT REGEXP_CONTAINS(COALESCE(TRIM(part.Part_No), ''), r'^9[0-9]{4}-BK'))
         AND COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0,
         SAFE_CAST(prod.Quantity AS FLOAT64), 0))       AS bottling_9part_qty,
  SUM(IF(wc.Workcenter_Group = 'Bottling' AND (STARTS_WITH(COALESCE(TRIM(part.Part_No), ''), '9') AND NOT REGEXP_CONTAINS(COALESCE(TRIM(part.Part_No), ''), r'^9[0-9]{4}-BK'))
         AND f5.part_key IS NOT NULL
         AND COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0,
         SAFE_CAST(prod.Quantity AS FLOAT64), 0))       AS bottling_9part_with_5_bom_qty

FROM prod

JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
  ON SAFE_CAST(prod.Workcenter_Key AS INT64) = SAFE_CAST(wc.Workcenter_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` part
  ON SAFE_CAST(prod.Part_Key AS INT64) = SAFE_CAST(part.Part_Key AS INT64)

LEFT JOIN nine_with_five_bom f5
  ON f5.part_key = SAFE_CAST(prod.Part_Key AS INT64)

WHERE prod.production_date IS NOT NULL
  AND wc.Workcenter_Group IS NOT NULL
  AND NOT (wc.Workcenter_Group = 'Bottling'
           AND STARTS_WITH(COALESCE(TRIM(part.Part_No), ''), '9')
           AND NOT REGEXP_CONTAINS(COALESCE(TRIM(part.Part_No), ''), r'^9[0-9]{4}-BK')
           AND prod.production_date < DATE '2026-11-01')

GROUP BY production_month, workcenter_group
ORDER BY production_month DESC, workcenter_group
