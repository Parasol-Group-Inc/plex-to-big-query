-- encap_daily_report — Plex-native "Actual" half of the Encap Daily Report
-- Google Sheet (reports-list/production.md, spreadsheets/encap_daily_report.md)
--
-- SCOPE DECISION 2026-08-21: this and its 3 sibling Daily Reports
-- (blending/labeling/packaging) were "no Plex analog" against Production
-- Yield (weight-centric, no attendance concept) until a screenshot of
-- Plex's own "Daily Shifts" UI report showed the real analog: a per-date,
-- per-workcenter rollup of Parts Produced/Scrapped, Hours, Efficiency, OEE.
--
-- CORRECTED SAME DAY: first built on `Part_v_Cell_Production`
-- (Quantity/Production_Date/Job_Op_Key only). A live screenshot of Plex's
-- own "Job Production" report — confirmed columns Job No/Part No/Rev/Op
-- No/Tracking No/Last Operation Completed/Workcenter/**Employee**/Record
-- Date/**Shift**/Quantity — matches `Part_v_Production` field-for-field
-- instead (`Record_By`, `Report_Shift`, `Record_Date`, `Workcenter_Key`,
-- `Job_Op_Key`, `Quantity`, `Rejected`). `Cell_Production` has no Employee/
-- Shift/Rejected columns at all — wrong table. Rebuilt on `Part_v_Production`.
--
-- This resolves 2 of the 3 "no Plex analog" gaps flagged this morning:
-- `employees`/`employee_count` (Record_By -> Personnel_v_Employee, same
-- INFERRED-join pattern already used and flagged in mfg_job_schedule_view.sql
-- for Started_By/Completed_By) gives a real attendance-adjacent signal, and
-- `scrap_qty` (the `Rejected` flag) gives a real, non-guessed scrap number.
-- Still NOT built: Planned Production Hours, Start-Up/Stop times, and a
-- true Call-Outs/OFF roster (a scheduled-vs-actually-showed-up comparison,
-- which `employees`/`employee_count` alone can't answer) — no Plex source
-- identified for any of those three specifically.
--
-- Grain kept at production date + workcenter (one row per line per day,
-- matching the sheet's own template) rather than splitting by `Report_Shift`
-- — shift is exposed as a distinct-list column instead of fragmenting grain,
-- since the sheet template doesn't ask for shift-level rows.
--
-- WORKCENTER MAPPING: filters `Part_v_Workcenter.Workcenter_Group =
-- 'Encapsulating'` (confirmed live value, catalog/plex_catalog_index.md),
-- which resolves to the confirmed `Encapsulation 1`-`Encapsulation 10`
-- roster. The sheet's own stations (1,2,4,5,7,8,9,10 — skipping 3 and 6)
-- are not filtered out here; if 3/6 are decommissioned/renamed in Plex,
-- real data will show 0 rows for them rather than a hardcoded guess.
--
-- UNCONFIRMED AGAINST REAL DATA: on the 2026-08-21 test tenant, all 16 real
-- jobs were freshly created that morning with 0 actual production logged
-- against any of them (Status=Scheduled, 0 hours) — so this table was
-- empty for a benign reason (nothing had run yet), not proof the table/
-- join is wrong. Needs re-checking once real production has actually
-- happened on this tenant.
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

  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0, SAFE_CAST(prod.Quantity AS FLOAT64), 0)) AS actual_qty,
  SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 1, SAFE_CAST(prod.Quantity AS FLOAT64), 0)) AS scrap_qty

FROM prod

JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Op` jo
  ON SAFE_CAST(prod.Job_Op_Key AS INT64) = SAFE_CAST(jo.Job_Op_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
  ON SAFE_CAST(prod.Workcenter_Key AS INT64) = wc.Workcenter_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
  ON jo.Job_Key = j.Job_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` part
  ON j.Part_Key = part.Part_Key

-- INFERRED join, not NetSuite/Plex-confirmed: Record_By is assumed to be a
-- Plexus_User_No, by analogy with the same assumption already made for
-- Job_Op.Started_By/Completed_By in mfg_job_schedule_view.sql.
LEFT JOIN `{gcp_project}.{dataset}.raw_Personnel_v_Employee` emp
  ON SAFE_CAST(prod.Record_By AS INT64) = emp.Plexus_User_No

WHERE wc.Workcenter_Group = 'Encapsulating'

GROUP BY prod.production_date, workcenter, workcenter_group
ORDER BY prod.production_date DESC, workcenter
