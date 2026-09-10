-- ═══════════════════════════════════════════════════════════════════════
-- GENERATED FILE — do not hand-edit. Regenerate with the generator noted
-- below after any change to the original.
--
--   original : revenue_vs_goal_view.sql
--   generated: v2_revenue_vs_goal_view.sql
--   generator: scripts/gen_v2_goal_views.py
--
-- The ONLY difference from the original is the goal source (the single FROM,
-- plus any header comment naming it, so the comments stay truthful):
--   original  reads  scorecard_goals              (spreadsheet ETL)
--   this file reads  v2_scorecard_goals_resolved  (app first, sheet fallback)
--
-- WHY A PARALLEL VIEW INSTEAD OF CHANGING THE ORIGINAL: Looker Studio data
-- sources point at the originals today. These v2 siblings let the scorecard
-- move over one tile at a time, and behave identically to the originals for
-- any goal the web app has not overridden. When the spreadsheet ETL is
-- sunset, delete the originals, drop the v2_ prefix, and delete this banner.
--
-- To see WHICH source fed a goal, query v2_scorecard_goals_resolved directly
-- - it carries a `goal_source` column ('app' or 'sheet'). Deliberately not
-- surfaced here, so this file stays a minimal diff from the original.
-- ═══════════════════════════════════════════════════════════════════════
-- v2_revenue_vs_goal_report — month-to-date shipping revenue against the
-- company revenue goal, with percent-to-goal (Plex-native source for the Vox
-- Nutrition Scorecard's "$4.7M Goal" and "88% to Goal" tiles — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-04. This is the first view in the pipeline that reads a
-- MAINTAINED table rather than Plex data.
--
-- WHERE THE GOAL COMES FROM: `{gcp_project}.{dataset}.v2_scorecard_goals_resolved`, a
-- plain BigQuery table whose source of truth is a Google Sheet, pushed here
-- by an Apps Script (see deploy/goals_sheet_to_bigquery.gs). It is NOT
-- created or written by this ETL — the pipeline only reads it. Created
-- 2026-09-04 in both PlexTest and PlexProd.
--
-- ⚠ THIS VIEW WILL FAIL TO CREATE IF scorecard_goals IS MISSING. It's an
-- external dependency, not a sibling view this run creates. If the table is
-- ever dropped, this view and its two siblings (sales_vs_goal_report,
-- production_vs_goal_report) stop being creatable — recreate the table from
-- the DDL in docs/reports/scorecard_goals.md first.
--
-- LEFT JOIN, NOT INNER — DELIBERATE: a month with real revenue but no goal
-- row yet still appears, with goal_value NULL and pct_to_goal NULL. An INNER
-- join would make the revenue tile silently vanish whenever somebody forgets
-- to fill in next month's goal, which is exactly the failure mode a
-- hand-maintained table invites. Actuals are Plex truth and should never
-- disappear because a spreadsheet is behind.
--
-- SAFE_DIVIDE, not `/` — a goal of 0 (or a row typed as 0 before being
-- filled in) yields NULL rather than a division error that breaks the whole
-- view.
--
-- SCOPE: revenue goals are company-wide, so this matches rows where `scope`
-- is NULL or empty. Per-rep goals live on sales_vs_goal_report instead.
--
-- Thin rollup over the sibling sales_revenue_summary_report — MUST stay
-- listed after it in reports/sales_orders.yaml's bq_view list.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per month.

WITH actual AS (
  SELECT
    revenue_month,
    SUM(shipping_revenue) AS actual_revenue,
    SUM(units_shipped)    AS units_shipped
  FROM `{gcp_project}.{dataset}.sales_revenue_summary_report`
  GROUP BY revenue_month
),

goal AS (
  SELECT
    period_month,
    SUM(goal_value) AS goal_value,
    ANY_VALUE(note) AS goal_note
  FROM `{gcp_project}.{dataset}.v2_scorecard_goals_resolved`
  WHERE LOWER(metric) = 'revenue'
    AND (scope IS NULL OR scope = '')
  GROUP BY period_month
)

SELECT
  a.revenue_month,
  a.actual_revenue,
  a.units_shipped,
  g.goal_value,
  SAFE_DIVIDE(a.actual_revenue, NULLIF(g.goal_value, 0))            AS pct_to_goal,
  (a.actual_revenue - g.goal_value)                                  AS variance_to_goal,
  g.goal_note

FROM actual a
LEFT JOIN goal g
  ON a.revenue_month = g.period_month

ORDER BY a.revenue_month DESC
