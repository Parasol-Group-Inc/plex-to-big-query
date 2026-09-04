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
-- BOOLEAN CONVENTION: Part_v_Production.Rejected uses -1 = true, the
-- convention confirmed live on the Part_v_* family (Part_v_Container.Active,
-- Container_Status.OK_Status). Do NOT copy the 1 = true convention confirmed
-- on the Sales_v_Shipper_Status / Sales_v_PO_Status tables used by the
-- sibling revenue views — this pipeline genuinely has both.
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
)

SELECT

  DATE_TRUNC(prod.production_date, MONTH)               AS production_month,
  wc.Workcenter_Group                                   AS workcenter_group,

  COUNT(DISTINCT prod.production_date)                  AS days_with_production,
  COUNT(DISTINCT wc.Workcenter_Key)                     AS workcenters_active,

  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0,
         SAFE_CAST(prod.Quantity AS FLOAT64), 0))       AS actual_qty,
  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = -1,
         SAFE_CAST(prod.Quantity AS FLOAT64), 0))       AS scrap_qty,
  SUM(SAFE_CAST(prod.Quantity AS FLOAT64))              AS total_qty,

  -- Scrap rate as a share of everything run, good and bad. Complements the
  -- FPY figure in quality_fpy_by_area_month_report, which is computed on the
  -- same table at the same grain and should agree with this.
  SAFE_DIVIDE(
    SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = -1,
           SAFE_CAST(prod.Quantity AS FLOAT64), 0)),
    NULLIF(SUM(SAFE_CAST(prod.Quantity AS FLOAT64)), 0)
  )                                                     AS scrap_rate

FROM prod

JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
  ON SAFE_CAST(prod.Workcenter_Key AS INT64) = SAFE_CAST(wc.Workcenter_Key AS INT64)

WHERE prod.production_date IS NOT NULL
  AND wc.Workcenter_Group IS NOT NULL

GROUP BY production_month, workcenter_group
ORDER BY production_month DESC, workcenter_group
