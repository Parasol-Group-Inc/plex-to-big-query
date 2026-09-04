-- blending_daily_report — Plex-native "Actual" half of the Blending Daily
-- Report Google Sheet (reports-list/production.md,
-- spreadsheets/blending_daily_report.md)
--
-- Same source table, correction history, and reasoning as
-- encap_daily_report_view.sql — see that file's header in full. Rebuilt
-- 2026-08-21 on `Part_v_Production` (not `Part_v_Cell_Production`) after a
-- live "Job Production" UI report screenshot confirmed Employee/Shift/
-- Record Date/Quantity columns matching `Part_v_Production` field-for-field.
--
-- WORKCENTER MAPPING: filters `Workcenter_Group IN ('Blending', 'Pre-Weigh')`
-- (confirmed live values) — the sheet's own "Blending 2/3/4/5" AND
-- "Pre-Weigh 1/2/3" stations are two different Plex workcenter groups that
-- this one report needs together, per the sheet's template (both weigh-out
-- and blending goals live in the same daily grid).
--
-- UNCONFIRMED AGAINST REAL DATA — same caveat as the other 3 Daily Reports
-- (see encap_daily_report_view.sql).
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
    p.Record_By,
    p.Report_Shift,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(p.Record_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(p.Record_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(p.Record_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ) AS production_date
  FROM `{gcp_project}.{dataset}.raw_Part_v_Production` p
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

  -- Plex represents boolean true as -1, not 1 (confirmed live 2026-08-11,
  -- see part_on_hand_inventory_view.sql/inventory_risk_analysis_view.sql's
  -- Active/OK_Status columns) — Rejected follows the same convention.
  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0, SAFE_CAST(prod.Quantity AS FLOAT64), 0)) AS actual_qty,
  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = -1, SAFE_CAST(prod.Quantity AS FLOAT64), 0)) AS scrap_qty

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

WHERE wc.Workcenter_Group IN ('Blending', 'Pre-Weigh')

GROUP BY prod.production_date, workcenter, workcenter_group
ORDER BY prod.production_date DESC, workcenter
