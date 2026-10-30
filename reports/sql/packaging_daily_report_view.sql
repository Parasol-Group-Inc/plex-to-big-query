-- packaging_daily_report — Plex-native "Actual" half of the Packaging Daily
-- Report Google Sheet (reports-list/production.md,
-- spreadsheets/packaging_daily_report.md)
--
-- Same source table, correction history, and reasoning as
-- encap_daily_report_view.sql — see that file's header in full. Rebuilt
-- 2026-08-21 on `Part_v_Production` (not `Part_v_Cell_Production`) after a
-- live "Job Production" UI report screenshot confirmed Employee/Shift/
-- Record Date/Quantity columns matching `Part_v_Production` field-for-field.
--
-- WORKCENTER MAPPING — DECIDED 2026-08-21: this was the hardest of the 4 to
-- place. "Packaging" is NOT a Plex workcenter group at all (confirmed live
-- groups: Blending, Bottling, Encapsulating, Labeling, Pre-Weigh,
-- Preparation, Printing, Rework, Scheduling) — it only exists as a
-- Department code (`PACK`) and a separate Part_Group value. But the
-- sheet's own line names (Line 1-5, Bulk, Gummy Line/Line 6, Powder Line,
-- Liquid Line) match the confirmed `Workcenter_Group = 'Bottling'` roster
-- almost exactly: `Bottling Line 1`-`Bottling Line 6`, `Bulk Room`,
-- `Powder Line`, `Liquid Line` (see catalog/plex_catalog_index.md). Built
-- on that basis rather than the PACK department or Packaging Part_Group,
-- neither of which is workcenter-shaped. The sheet's "Line" numbering
-- still doesn't confirm 1:1 against `Bottling Line N` — flagged in
-- spreadsheets/packaging_daily_report.md as needing real data to verify.
--
-- UNCONFIRMED AGAINST REAL DATA — same caveat as the other 3 Daily Reports
-- (see encap_daily_report_view.sql).
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
-- Not re-extracted — bq_view entry in reports/work_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per workcenter per production date.

WITH prod AS (
  SELECT
    p.Quantity,
    p.Rejected,
    p.Job_Op_Key,
    p.Workcenter_Key,
    p.Part_Key,
    p.Record_By,
    p.Report_Shift,
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

  prod.production_date,
  wc.Name                                               AS workcenter,
  wc.Workcenter_Group                                   AS workcenter_group,

  STRING_AGG(DISTINCT part.Part_No, ', ' ORDER BY part.Part_No) AS parts_run,
  COUNT(DISTINCT j.Job_Key)                             AS job_count,

  COUNT(DISTINCT emp.Plexus_User_No)                    AS employee_count,
  STRING_AGG(DISTINCT emp.Common_Name, ', ' ORDER BY emp.Common_Name) AS employees,
  STRING_AGG(DISTINCT prod.Report_Shift, ', ' ORDER BY prod.Report_Shift) AS shifts,

  -- Rejected is 1 on a rejected record, NOT -1: checked 2026-09-24 against the
  -- only real rejected row in PlexTest (Bottling Line 1, 500 units). The old
  -- `= -1` test rested on a 2026-08-11 "convention" that the container flags
  -- had already disproved (docs/CHEATSHEET.md, Booleans), and it counted no
  -- scrap at all. `!= 0` catches either value, so scrap is never dropped.
  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0, SAFE_CAST(prod.Quantity AS FLOAT64), 0)) AS actual_qty,
  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) != 0, SAFE_CAST(prod.Quantity AS FLOAT64), 0)) AS scrap_qty,

  -- Added 2026-10-30 (CUTOVER above): good output on 9-parts (bulk cases
  -- excluded), and the part of it on 9-parts that still have a 5-part BOM.
  SUM(IF((STARTS_WITH(COALESCE(TRIM(prod_part.Part_No), ''), '9') AND NOT REGEXP_CONTAINS(COALESCE(TRIM(prod_part.Part_No), ''), r'^9[0-9]{4}-BK'))
         AND COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0,
         SAFE_CAST(prod.Quantity AS FLOAT64), 0)) AS bottling_9part_qty,
  SUM(IF((STARTS_WITH(COALESCE(TRIM(prod_part.Part_No), ''), '9') AND NOT REGEXP_CONTAINS(COALESCE(TRIM(prod_part.Part_No), ''), r'^9[0-9]{4}-BK')) AND f5.part_key IS NOT NULL
         AND COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0,
         SAFE_CAST(prod.Quantity AS FLOAT64), 0)) AS bottling_9part_with_5_bom_qty

FROM prod

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo
  ON SAFE_CAST(prod.Job_Op_Key AS INT64) = SAFE_CAST(jo.Job_Op_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
  ON SAFE_CAST(prod.Workcenter_Key AS INT64) = wc.Workcenter_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
  ON SAFE_CAST(jo.Job_Key AS INT64) = SAFE_CAST(j.Job_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` part
  ON SAFE_CAST(j.Part_Key AS INT64) = SAFE_CAST(part.Part_Key AS INT64)

-- INFERRED join, not NetSuite/Plex-confirmed — see encap_daily_report_view.sql.
LEFT JOIN `{gcp_project}.{dataset}.raw_Personnel_v_Employee` emp
  ON SAFE_CAST(prod.Record_By AS INT64) = emp.Plexus_User_No

-- The part the production record names, for the 9-part rule above.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` prod_part
  ON SAFE_CAST(prod.Part_Key AS INT64) = SAFE_CAST(prod_part.Part_Key AS INT64)

LEFT JOIN nine_with_five_bom f5
  ON f5.part_key = SAFE_CAST(prod.Part_Key AS INT64)

WHERE wc.Workcenter_Group = 'Bottling'
  AND (NOT STARTS_WITH(COALESCE(TRIM(prod_part.Part_No), ''), '9')
       OR REGEXP_CONTAINS(COALESCE(TRIM(prod_part.Part_No), ''), r'^9[0-9]{4}-BK')
       OR prod.production_date >= DATE '2026-11-01')

GROUP BY prod.production_date, workcenter, workcenter_group
ORDER BY prod.production_date DESC, workcenter
