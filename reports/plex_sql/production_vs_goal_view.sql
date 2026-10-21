-- production_vs_goal_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/production_vs_goal_view.sql
-- confidence: low
-- plex_views: Part_v_Production, Part_v_Workcenter
-- notes: Goals (scorecard_goals_resolved) are typed by people, not in Plex; replaced by an EMPTY placeholder CTE, so goal columns are NULL until you paste real rows in. Actuals inline production_monthly_by_workcenter_group_report.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per month x workcenter group (actuals FULL OUTER JOIN goals).
-- scope must match Workcenter_Group exactly (Plex says 'Encapsulating', scorecard tile says 'Encapsulation').

WITH prod AS (
  SELECT
    pr.Quantity,
    pr.Rejected,
    pr.Workcenter_Key,
    CAST(pr.Record_Date AS date) AS production_date
  FROM Part_v_Production AS pr
),

-- Upstream: production_monthly_by_workcenter_group_report
monthly AS (
  SELECT
    DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1) AS production_month,
    wc.Workcenter_Group                                                   AS workcenter_group,
    SUM(CASE WHEN ISNULL(pd.Rejected, 0) = 0 THEN pd.Quantity ELSE 0 END)  AS actual_qty,
    SUM(CASE WHEN ISNULL(pd.Rejected, 0) <> 0 THEN pd.Quantity ELSE 0 END) AS scrap_qty,
    SUM(pd.Quantity)                                                      AS total_qty
  FROM prod AS pd
  JOIN Part_v_Workcenter AS wc
    ON pd.Workcenter_Key = wc.Workcenter_Key
  WHERE pd.production_date IS NOT NULL
    AND wc.Workcenter_Group IS NOT NULL
  GROUP BY DATEFROMPARTS(YEAR(pd.production_date), MONTH(pd.production_date), 1), wc.Workcenter_Group
),

actual AS (
  SELECT
    mo.production_month,
    mo.workcenter_group,
    SUM(mo.actual_qty) AS actual_qty,
    SUM(mo.scrap_qty)  AS scrap_qty,
    SUM(mo.total_qty)  AS total_qty
  FROM monthly AS mo
  GROUP BY mo.production_month, mo.workcenter_group
),

-- PLACEHOLDER: scorecard_goals_resolved is NOT in Plex (manual-data app / Google Sheet).
-- Empty on purpose. To test with goals, replace the WHERE 1 = 0 row source with e.g.
--   SELECT * FROM (VALUES ('production', CAST('2026-10-01' AS date), 'Encapsulating', 1000000.0, 'note'))
--     AS v(metric, period_month, scope, goal_value, note)
sg AS (
  SELECT
    CAST('production' AS varchar(50)) AS metric,
    CAST(NULL AS date)                AS period_month,
    CAST(NULL AS varchar(100))        AS scope,
    CAST(NULL AS float)               AS goal_value,
    CAST(NULL AS varchar(500))        AS note
  WHERE 1 = 0
),

goal AS (
  SELECT
    s.period_month,
    s.scope           AS workcenter_group,
    SUM(s.goal_value) AS goal_value,
    MAX(s.note)       AS goal_note
  FROM sg AS s
  WHERE LOWER(s.metric) = 'production'
    AND s.scope IS NOT NULL
    AND s.scope <> ''
  GROUP BY s.period_month, s.scope
)

SELECT
  COALESCE(a.production_month, g.period_month)                  AS production_month,
  COALESCE(a.workcenter_group, g.workcenter_group)              AS workcenter_group,
  ISNULL(a.actual_qty, 0)                                       AS actual_qty,
  ISNULL(a.scrap_qty, 0)                                        AS scrap_qty,
  ISNULL(a.total_qty, 0)                                        AS total_qty,
  g.goal_value,
  ISNULL(a.actual_qty, 0) / NULLIF(g.goal_value, 0)             AS pct_to_goal,
  (ISNULL(a.actual_qty, 0) - g.goal_value)                      AS variance_to_goal,
  CASE WHEN a.workcenter_group IS NULL THEN 1 ELSE 0 END        AS goal_without_production,
  CASE WHEN g.workcenter_group IS NULL THEN 1 ELSE 0 END        AS production_without_goal,
  g.goal_note
FROM actual AS a
FULL OUTER JOIN goal AS g
  ON a.production_month = g.period_month
 AND a.workcenter_group = g.workcenter_group
ORDER BY production_month DESC, workcenter_group;
