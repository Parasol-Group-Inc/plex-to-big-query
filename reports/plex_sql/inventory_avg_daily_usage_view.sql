-- inventory_avg_daily_usage_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/inventory_avg_daily_usage_view.sql
-- confidence: high
-- plex_views: Part_v_Cell_Production, Part_v_Cell_Depletion, Part_v_Part
-- notes: Upstream inventory_activity_report inlined as CTEs; day-count rule (finished month = calendar days, current month = day of month, future = NULL average) kept.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per (part, month), in the part's own unit. Do not sum across parts.
WITH production_dated AS (
  SELECT cp.Part_Key AS Part_Key, cp.Quantity AS Quantity, CAST(cp.Production_Date AS date) AS production_date
  FROM Part_v_Cell_Production AS cp
),
depletion_dated AS (
  SELECT cd.Part_Key AS Part_Key, cd.Quantity AS Quantity, CAST(cd.Production_Date AS date) AS depletion_date
  FROM Part_v_Cell_Depletion AS cd
),
production_monthly AS (
  SELECT pd.Part_Key,
         DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1) AS activity_month,
         SUM(pd.Quantity) AS produced_quantity
  FROM production_dated AS pd
  WHERE pd.production_date IS NOT NULL
  GROUP BY pd.Part_Key, DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1)
),
depletion_monthly AS (
  SELECT dd.Part_Key,
         DATEFROMPARTS(YEAR(dd.depletion_date), MONTH(dd.depletion_date), 1) AS activity_month,
         SUM(dd.Quantity) AS depleted_quantity
  FROM depletion_dated AS dd
  WHERE dd.depletion_date IS NOT NULL
  GROUP BY dd.Part_Key, DATEFROMPARTS(YEAR(dd.depletion_date), MONTH(dd.depletion_date), 1)
),
-- inlined inventory_activity_report
activity AS (
  SELECT
    COALESCE(prod.Part_Key, dep.Part_Key)             AS part_key,
    p.Part_No                                         AS part_number,
    p.Name                                            AS part_name,
    COALESCE(prod.activity_month, dep.activity_month) AS activity_month,
    COALESCE(dep.depleted_quantity, 0)                AS depleted_quantity
  FROM production_monthly AS prod
  FULL OUTER JOIN depletion_monthly AS dep
    ON prod.Part_Key = dep.Part_Key AND prod.activity_month = dep.activity_month
  LEFT JOIN Part_v_Part AS p
    ON COALESCE(prod.Part_Key, dep.Part_Key) = p.Part_Key
),
cur AS (
  SELECT DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1) AS this_month,
         DAY(GETDATE()) AS today_day
),
usage AS (
  SELECT
    a.part_key, a.part_number, a.part_name, a.activity_month, a.depleted_quantity,
    CASE
      WHEN a.activity_month = c.this_month THEN c.today_day            -- month in progress: days through today
      WHEN a.activity_month < c.this_month
        THEN DATEDIFF(day, a.activity_month, DATEADD(month, 1, a.activity_month))  -- finished month: calendar days
      ELSE 0                                                           -- future month: NULL average
    END AS days_in_period
  FROM activity AS a
  CROSS JOIN cur AS c
)
SELECT
  u.part_key,
  u.part_number,
  u.part_name,
  p.Unit                                  AS unit,
  u.activity_month,
  u.depleted_quantity,
  u.days_in_period,
  CASE WHEN u.activity_month = c.this_month THEN 1 ELSE 0 END AS is_month_in_progress,
  u.depleted_quantity / NULLIF(u.days_in_period, 0) AS avg_daily_usage
FROM usage AS u
CROSS JOIN cur AS c
LEFT JOIN Part_v_Part AS p
  ON u.part_key = p.Part_Key;
