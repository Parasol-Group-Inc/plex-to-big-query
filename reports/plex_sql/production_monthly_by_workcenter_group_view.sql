-- production_monthly_by_workcenter_group_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/production_monthly_by_workcenter_group_view.sql
-- confidence: high
-- plex_views: Part_v_Production, Part_v_Workcenter
-- notes: Mechanical translation; DATE_TRUNC(MONTH) becomes DATEFROMPARTS(YEAR, MONTH, 1).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per month x workcenter group. Rejected <> 0 counts as scrap.

WITH prod AS (
  SELECT
    pr.Quantity,
    pr.Rejected,
    pr.Workcenter_Key,
    pr.Part_Key,
    CAST(pr.Record_Date AS date) AS production_date
  FROM Part_v_Production AS pr
)

SELECT
  DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1) AS production_month,
  wc.Workcenter_Group                                                   AS workcenter_group,
  COUNT(DISTINCT pd.production_date)                                    AS days_with_production,
  COUNT(DISTINCT wc.Workcenter_Key)                                     AS workcenters_active,
  SUM(CASE WHEN ISNULL(pd.Rejected, 0) = 0 THEN pd.Quantity ELSE 0 END)  AS actual_qty,
  SUM(CASE WHEN ISNULL(pd.Rejected, 0) <> 0 THEN pd.Quantity ELSE 0 END) AS scrap_qty,
  SUM(pd.Quantity)                                                      AS total_qty,
  SUM(CASE WHEN ISNULL(pd.Rejected, 0) <> 0 THEN pd.Quantity ELSE 0 END)
    / NULLIF(SUM(pd.Quantity), 0)                                       AS scrap_rate
FROM prod AS pd
JOIN Part_v_Workcenter AS wc
  ON pd.Workcenter_Key = wc.Workcenter_Key
LEFT JOIN Part_v_Part AS pp
  ON pd.Part_Key = pp.Part_Key
WHERE pd.production_date IS NOT NULL
  AND wc.Workcenter_Group IS NOT NULL
-- Bottling 9-parts are double credit for their 5 part (Jennilyn, 2026-10-22).
  -- Bulk cases (9xxxx-BK) have no 5-part job and still count.
  AND NOT (wc.Workcenter_Group = 'Bottling' AND LTRIM(ISNULL(pp.Part_No, '')) LIKE '9%'
           AND LTRIM(ISNULL(pp.Part_No, '')) NOT LIKE '9[0-9][0-9][0-9][0-9]-BK%')
GROUP BY DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1), wc.Workcenter_Group
ORDER BY production_month DESC, workcenter_group;
