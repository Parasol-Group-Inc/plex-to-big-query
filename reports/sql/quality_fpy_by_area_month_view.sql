-- quality_fpy_by_area_month_report — First Pass Yield and DPMO by
-- production area (Workcenter_Group) and month (Plex-native candidate for
-- the Vox Nutrition Scorecard's YTD FPYs tiles — Quality_Looker_DB - YTD
-- FPYs, 9 charts, the 2nd-highest-usage source in the whole scorecard —
-- see score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- FPY needs no assumption at all: computed directly from Part_v_Production
-- (Quantity/Rejected), the same columns already used by the 4 Daily
-- Reports and mfg_job_schedule_success_metrics_report's Yield calc.
--
-- DPMO — BEST-CRITERIA PLACEHOLDER, DECIDED 2026-09-01: the DPMO formula
-- needs an "opportunities per unit" constant (how many distinct ways a
-- single unit could fail) that is a quality-engineering process
-- definition, not something any Plex table stores. Rather than leave this
-- tile blank, OPPORTUNITIES_PER_UNIT below is hardcoded to 1 (each
-- rejected unit counted as exactly 1 defect opportunity) — a single named
-- constant, trivial to change once Quality provides a real per-process
-- figure. Treat this DPMO column as provisional until that happens.
--
-- SIGMA DELIBERATELY NOT COMPUTED: converting DPMO to a Sigma level needs
-- either an inverse-normal-distribution lookup or a well-tested closed-form
-- approximation — this is regulatory/cGMP-adjacent territory (see this
-- folder's Field Guide), and a hand-rolled approximation formula risks
-- being subtly wrong in a way that looks perfectly plausible. Left out
-- entirely rather than shipped unverified; add it once DPMO's own
-- opportunities-per-unit input is real, from a proper conversion table or
-- BigQuery's statistical functions, not guessed here.
--
-- FIXED 2026-09-01, same day as first written: the first version joined
-- Part_v_Production to Part_v_Job_Op (copied from the Daily Reports'
-- pattern) purely to reach Workcenter_Key — but Part_v_Production already
-- carries Workcenter_Key directly, and that Job_Op join was an INNER JOIN
-- silently dropping every row once real production data landed (this
-- tenant's real Job_Op_Keys in Part_v_Production have since aged out of
-- the current Part_v_Job_Op extract). Removed the unused Job_Op join
-- entirely — this view never needed it. Same root cause documented in
-- full in encap_daily_report_view.sql's header, which got the equivalent
-- fix (LEFT JOIN instead, since it still needs Job_Op for Job/Part).
--
-- Not re-extracted — bq_view entry in reports/work_orders.yaml, same raw
-- tables (Part_v_Production, Part_v_Workcenter) as the 4
-- Daily Reports.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (Workcenter_Group, month).

WITH

prod AS (
  SELECT
    p.Quantity,
    p.Rejected,
    p.Job_Op_Key,
    p.Workcenter_Key,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(p.Record_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(p.Record_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(p.Record_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ) AS production_date
  FROM `{gcp_project}.{dataset}.raw_Part_v_Production` p
),

by_area_month AS (
  SELECT
    wc.Workcenter_Group                                                                                  AS area,
    DATE_TRUNC(prod.production_date, MONTH)                                                               AS fpy_month,
    SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = 0, SAFE_CAST(prod.Quantity AS FLOAT64), 0))    AS good_qty,
    SUM(IF(COALESCE(SAFE_CAST(prod.Rejected AS INT64), 0) = -1, SAFE_CAST(prod.Quantity AS FLOAT64), 0))   AS rejected_qty,
    SUM(SAFE_CAST(prod.Quantity AS FLOAT64))                                                                AS total_qty
  FROM prod
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` wc
    ON SAFE_CAST(prod.Workcenter_Key AS INT64) = wc.Workcenter_Key
  WHERE prod.production_date IS NOT NULL
  GROUP BY area, fpy_month
)

SELECT
  area,
  fpy_month,
  total_qty,
  good_qty,
  rejected_qty,
  SAFE_DIVIDE(good_qty, total_qty)                            AS fpy,

  -- OPPORTUNITIES_PER_UNIT = 1 — see header comment.
  SAFE_DIVIDE(rejected_qty, total_qty * 1) * 1000000          AS dpmo_provisional

FROM by_area_month
ORDER BY fpy_month DESC, area
