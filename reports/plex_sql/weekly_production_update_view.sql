-- weekly_production_update_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/weekly_production_update_view.sql
-- confidence: medium
-- plex_views: Part_v_Production, Part_v_Job_Op, Part_v_Workcenter
-- notes: "Today" is the Plex SQL server's date (BigQuery used America/Denver); week starts Monday via DATEDIFF from 1900-01-01 (a Monday), independent of DATEFIRST.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per department (Encap, Bottling, Labeling, Printing): week-to-date and month-to-date good quantity.

WITH
today AS (
  SELECT CAST(GETDATE() AS date) AS today_date
),

bounds AS (
  SELECT
    t.today_date,
    DATEADD(day, -(DATEDIFF(day, '19000101', t.today_date) % 7), t.today_date) AS week_start,
    DATEFROMPARTS(YEAR(t.today_date), MONTH(t.today_date), 1)                  AS month_start
  FROM today AS t
),

prod AS (
  SELECT
    pr.Quantity,
    pr.Rejected,
    pr.Job_Op_Key,
    CAST(pr.Record_Date AS date) AS production_date
  FROM Part_v_Production AS pr
),

by_department AS (
  SELECT
    CASE wc.Workcenter_Group
      WHEN 'Encapsulating' THEN 'Encap'
      ELSE wc.Workcenter_Group
    END AS department,
    pd.production_date,
    CASE WHEN ISNULL(pd.Rejected, 0) = 0 THEN pd.Quantity ELSE 0 END AS non_rejected_qty
  FROM prod AS pd
  JOIN Part_v_Job_Op AS jo
    ON pd.Job_Op_Key = jo.Job_Op_Key
  JOIN Part_v_Workcenter AS wc
    ON jo.Workcenter_Key = wc.Workcenter_Key
  WHERE wc.Workcenter_Group IN ('Encapsulating', 'Bottling', 'Labeling', 'Printing')
),

-- Fixed department list so every department shows even with no production.
departments AS (
  SELECT v.department
  FROM (VALUES ('Encap'), ('Bottling'), ('Labeling'), ('Printing')) AS v(department)
)

SELECT
  d.department,
  SUM(CASE WHEN bd.production_date >= b.week_start
            AND bd.production_date <= b.today_date
           THEN bd.non_rejected_qty ELSE 0 END)                AS wtd_actual_qty,
  SUM(CASE WHEN bd.production_date >= b.month_start
            AND bd.production_date <= b.today_date
           THEN bd.non_rejected_qty ELSE 0 END)                AS mtd_actual_qty,
  MAX(1.0 * DAY(b.today_date) / NULLIF(DAY(EOMONTH(b.today_date)), 0)) AS pct_of_month_complete
FROM departments AS d
CROSS JOIN bounds AS b
LEFT JOIN by_department AS bd
  ON bd.department = d.department
GROUP BY d.department
ORDER BY d.department;
