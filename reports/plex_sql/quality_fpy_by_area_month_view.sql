-- quality_fpy_by_area_month_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/quality_fpy_by_area_month_view.sql
-- confidence: high
-- plex_views: Part_v_Production, Part_v_Workcenter
-- notes: Mechanical translation; DATE_TRUNC(MONTH) becomes DATEFROMPARTS(YEAR, MONTH, 1).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per workcenter group (area) x month.
-- FPY = good qty / total qty; dpmo_provisional = rejected per million units.

WITH
prod AS (
  SELECT
    pr.Quantity,
    pr.Rejected,
    pr.Job_Op_Key,
    pr.Workcenter_Key,
    CAST(pr.Record_Date AS date) AS production_date
  FROM Part_v_Production AS pr
),

by_area_month AS (
  SELECT
    wc.Workcenter_Group                                                         AS area,
    DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1)       AS fpy_month,
    SUM(CASE WHEN ISNULL(pd.Rejected, 0) = 0 THEN pd.Quantity ELSE 0 END)       AS good_qty,
    SUM(CASE WHEN ISNULL(pd.Rejected, 0) <> 0 THEN pd.Quantity ELSE 0 END)      AS rejected_qty,
    SUM(pd.Quantity)                                                            AS total_qty
  FROM prod AS pd
  JOIN Part_v_Workcenter AS wc
    ON pd.Workcenter_Key = wc.Workcenter_Key
  WHERE pd.production_date IS NOT NULL
  GROUP BY wc.Workcenter_Group, DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1)
)

SELECT
  a.area,
  a.fpy_month,
  a.total_qty,
  a.good_qty,
  a.rejected_qty,
  a.good_qty / NULLIF(a.total_qty, 0)                    AS fpy,
  a.rejected_qty / NULLIF(a.total_qty * 1, 0) * 1000000  AS dpmo_provisional
FROM by_area_month AS a
ORDER BY a.fpy_month DESC, a.area;
