-- encap_daily_report — Plex-native "Actual" half of the Encap Daily Report
-- Google Sheet (reports-list/production.md, spreadsheets/encap_daily_report.md)
--
-- SCOPE DECISION 2026-08-21: this and its 3 sibling Daily Reports
-- (blending/labeling/packaging) were "no Plex analog" against Production
-- Yield (weight-centric, no attendance concept) until a screenshot of
-- Plex's own "Daily Shifts" UI report showed the real analog: a per-date,
-- per-workcenter rollup of Parts Produced/Scrapped, Hours, Efficiency, OEE.
-- Only the "Parts Produced" half is built here — `Part_v_Cell_Production`
-- (Quantity, Production_Date, Job_Op_Key) is confirmed live schema and
-- gives exactly that. NOT built, not guessed: Planned Production Hours,
-- Start-Up/Stop times, and the employee Call Outs/OFF attendance roster —
-- same category as MFG Job Schedule's manual-only columns, no Plex source
-- identified. Scrap quantity was investigated and has no direct Job_Op/
-- Cell_Production column; the only scrap-quantity field found
-- (`Part_v_Container_Scrap_Allocation.Quantity`) requires container-level
-- serial tracing, a separate and heavier build — not attempted here.
--
-- WORKCENTER MAPPING: filters `Part_v_Workcenter.Workcenter_Group =
-- 'Encapsulating'` (confirmed live value, catalog/plex_catalog_index.md),
-- which resolves to the confirmed `Encapsulation 1`-`Encapsulation 10`
-- roster. The sheet's own stations (1,2,4,5,7,8,9,10 — skipping 3 and 6)
-- are not filtered out here; if 3/6 are decommissioned/renamed in Plex,
-- real data will show 0 rows for them rather than a hardcoded guess.
--
-- UNCONFIRMED AGAINST REAL DATA: whether Part_v_Cell_Production is
-- actually populated for this tenant's encapsulation jobs at all — flagged
-- in every Daily Report doc as needing real (non-template) data to verify
-- before trusting row counts.
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

WHERE wc.Workcenter_Group = 'Encapsulating'

GROUP BY cp.production_date, workcenter, workcenter_group
ORDER BY cp.production_date DESC, workcenter
