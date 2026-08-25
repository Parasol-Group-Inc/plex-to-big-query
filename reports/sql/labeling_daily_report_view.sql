-- labeling_daily_report — Plex-native "Actual" half of the Labeling Daily
-- Report Google Sheet (reports-list/production.md,
-- spreadsheets/labeling_daily_report.md)
--
-- Same source table, correction history, and reasoning as
-- encap_daily_report_view.sql — see that file's header in full. Rebuilt
-- 2026-08-21 on `Part_v_Production` (not `Part_v_Cell_Production`) after a
-- live "Job Production" UI report screenshot confirmed Employee/Shift/
-- Record Date/Quantity columns matching `Part_v_Production` field-for-field.
--
-- Also NOT built: the sheet's three shift-checkpoint timestamps (6:30 AM/
-- 8:45 AM/12:15 PM) and "# Of Orders Complete" — no confirmed Plex analog
-- identified for either. `Report_Shift` (exposed as `shifts` below) is a
-- shift LABEL, not a checkpoint time, so it doesn't fill this gap. "# Of
-- Orders Complete" is conceptually close to `labeling_open_work_orders_report`'s
-- open-job count, but that counts OPEN jobs, not completions — a genuinely
-- different query, not approximated here.
--
-- WORKCENTER MAPPING: filters `Workcenter_Group = 'Labeling'` (confirmed
-- live value), resolving to `Labeling 1`-`Labeling 6` plus `First 48` — a
-- direct match to the sheet's own "Line 1-6" numbering (the best-mapped of
-- the 4 Daily Reports per spreadsheets/labeling_daily_report.md).
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

JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo
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

WHERE wc.Workcenter_Group = 'Labeling'

GROUP BY prod.production_date, workcenter, workcenter_group
ORDER BY prod.production_date DESC, workcenter
