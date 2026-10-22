-- scorecard_goals_resolved — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/scorecard_goals_resolved_view.sql
-- confidence: low
-- plex_views: (none)
-- notes: Entirely non-Plex: goals are typed by people into BigQuery tables (scorecard_goals_app, scorecard_goals); this is an empty placeholder with the same columns.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Goals are typed by people in BigQuery (the manual-data app writes scorecard_goals_app; scorecard_goals is the legacy
-- table). The view takes the app's newest row per (metric, month, scope), falling back to the legacy table.
-- Plex holds none of this data, so there is nothing to translate; the SELECT below only returns the column shape.
SELECT
  g.metric       AS metric,
  g.period_month AS period_month,
  g.scope        AS scope,
  g.goal_value   AS goal_value,
  g.unit         AS unit,
  g.note         AS note,
  g.updated_by   AS updated_by,
  g.updated_at   AS updated_at,
  g.goal_source  AS goal_source
FROM (
  SELECT
    CAST(NULL AS varchar(100))  AS metric,
    CAST(NULL AS date)          AS period_month,
    CAST(NULL AS varchar(200))  AS scope,
    CAST(NULL AS float)         AS goal_value,
    CAST(NULL AS varchar(50))   AS unit,
    CAST(NULL AS varchar(500))  AS note,
    CAST(NULL AS varchar(200))  AS updated_by,
    CAST(NULL AS datetime)      AS updated_at,
    CAST(NULL AS varchar(10))   AS goal_source
) AS g
WHERE 1 = 0
