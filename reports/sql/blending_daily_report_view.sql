-- blending_daily_report — Plex-native "Actual" half of the Blending Daily
-- Report Google Sheet (reports-list/production.md,
-- spreadsheets/blending_daily_report.md)
--
-- Same scope decision and Cell_Production approach as encap_daily_report —
-- see that file's header for the full reasoning (Daily Shifts UI report as
-- the confirming lead, Planned Hours/attendance/scrap explicitly NOT built).
--
-- WORKCENTER MAPPING: filters `Workcenter_Group IN ('Blending', 'Pre-Weigh')`
-- (confirmed live values) — the sheet's own "Blending 2/3/4/5" AND
-- "Pre-Weigh 1/2/3" stations are two different Plex workcenter groups that
-- this one report needs together, per the sheet's template (both weigh-out
-- and blending goals live in the same daily grid).
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

WHERE wc.Workcenter_Group IN ('Blending', 'Pre-Weigh')

GROUP BY cp.production_date, workcenter, workcenter_group
ORDER BY cp.production_date DESC, workcenter
