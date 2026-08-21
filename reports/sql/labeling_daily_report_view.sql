-- labeling_daily_report — Plex-native "Actual" half of the Labeling Daily
-- Report Google Sheet (reports-list/production.md,
-- spreadsheets/labeling_daily_report.md)
--
-- Same scope decision and Cell_Production approach as encap_daily_report —
-- see that file's header for the full reasoning (Daily Shifts UI report as
-- the confirming lead, Planned Hours/attendance/scrap explicitly NOT built).
-- Also NOT built: the sheet's three shift-checkpoint timestamps (6:30 AM/
-- 8:45 AM/12:15 PM) and "# Of Orders Complete" — no confirmed Plex analog
-- identified for either. "# Of Orders Complete" is conceptually close to
-- `labeling_open_work_orders_report`'s open-job count, but that report
-- counts OPEN jobs, not completions — a genuinely different query, not
-- approximated here.
--
-- WORKCENTER MAPPING: filters `Workcenter_Group = 'Labeling'` (confirmed
-- live value), resolving to `Labeling 1`-`Labeling 6` plus `First 48` — a
-- direct match to the sheet's own "Line 1-6" numbering (the best-mapped of
-- the 4 Daily Reports per spreadsheets/labeling_daily_report.md).
--
-- UNCONFIRMED AGAINST REAL DATA — same caveat as the other 3 Daily Reports.
--
-- Not re-extracted — bq_view entry in reports/work_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per workcenter per production date.

WITH cell_prod AS (
  SELECT
    cp.Quantity,
    cp.Job_Op_Key,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(cp.Production_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(cp.Production_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(cp.Production_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ) AS production_date
  FROM `{gcp_project}.{dataset}.raw_Part_v_Cell_Production` cp
)

SELECT

  cp.production_date,
  wc.Name                                               AS workcenter,
  wc.Workcenter_Group                                   AS workcenter_group,

  STRING_AGG(DISTINCT p.Part_No, ', ' ORDER BY p.Part_No) AS parts_run,
  COUNT(DISTINCT j.Job_Key)                             AS job_count,
  SUM(SAFE_CAST(cp.Quantity AS FLOAT64))                AS actual_qty

FROM cell_prod cp

JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo
  ON SAFE_CAST(cp.Job_Op_Key AS INT64) = SAFE_CAST(jo.Job_Op_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
  ON SAFE_CAST(jo.Workcenter_Key AS INT64) = wc.Workcenter_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
  ON jo.Job_Key = j.Job_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON j.Part_Key = p.Part_Key

WHERE wc.Workcenter_Group = 'Labeling'

GROUP BY cp.production_date, workcenter, workcenter_group
ORDER BY cp.production_date DESC, workcenter
