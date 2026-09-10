-- v2_scorecard_goals_resolved — ONE goal per (metric, month, scope), taken
-- from the Apps Script web app if it has one, and otherwise from the
-- spreadsheet ETL.
--
-- NEW 2026-09-09. This is the migration seam between two goal sources that
-- both need to keep working:
--
--   scorecard_goals_app  — written by the Apps Script WEB APP (a form people
--                          fill in; deploy/goals_web_app/). Append-only.
--   scorecard_goals      — written by the SPREADSHEET ETL
--                          (deploy/goals_sheet_to_bigquery.gs, WRITE_TRUNCATE
--                          from a Google Sheet). The current source of truth.
--
-- Precedence: **app first, sheet as fallback.** A key present in the app table
-- wins; a key absent there falls through to the sheet, so nothing goes blank
-- while the two run side by side. When the spreadsheet ETL is sunset, delete
-- the `sheet` branch below and this view becomes a thin read of the app table
-- — no consumer has to change.
--
-- WHY APPEND-ONLY ON THE APP SIDE: the web app never updates or deletes a
-- row, it only adds one, and the newest `updated_at` per key wins. Two people
-- editing the same goal minutes apart cannot lose each other's write the way
-- a read-modify-write would, and every edit stays visible as history. The
-- cost is this dedupe, which is cheap on a table of goals.
--
-- DELETES ARE TOMBSTONES: the app writes `is_deleted = TRUE` to retract an
-- override. A tombstone means "the app has nothing to say about this key", so
-- it falls back to the sheet rather than blanking the goal. That is the only
-- sensible reading while both sources are live — a retracted override should
-- restore the spreadsheet value, not erase the tile.
--
-- ⚠ BOTH TABLES ARE HAND-CREATED AND NOT MANAGED BY TERRAFORM, and this view
-- fails to create if either is missing. `scorecard_goals` predates this
-- (docs/reports/scorecard_goals.md); `scorecard_goals_app` was created
-- 2026-09-09 in both datasets. Rebuild DDL for both is in that doc.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml AND
-- reports/work_orders.yaml. It is listed in both because goal views live in
-- both pipelines and each must be able to create its own dependencies
-- without waiting on the other's run; the SQL is identical, so whichever
-- runs second simply replaces an identical view.
-- MUST be listed BEFORE any v2_*_vs_goal_report in the same config.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (metric, period_month, scope).

WITH

app_latest AS (
  SELECT
    metric,
    period_month,
    scope,
    goal_value,
    unit,
    note,
    updated_by,
    updated_at,
    is_deleted
  FROM (
    SELECT
      *,
      ROW_NUMBER() OVER (
        PARTITION BY LOWER(TRIM(metric)), period_month, IFNULL(TRIM(scope), '')
        -- Newest edit wins. updated_at is stamped by the web app, not by the
        -- client clock of whoever filled the form in.
        ORDER BY updated_at DESC
      ) AS rn
    FROM `{gcp_project}.{dataset}.scorecard_goals_app`
  )
  WHERE rn = 1
),

-- Live overrides only. Tombstones are dropped here so the sheet branch can
-- supply the key instead.
app AS (
  SELECT * FROM app_latest
  WHERE NOT COALESCE(is_deleted, FALSE)
),

sheet AS (
  SELECT
    metric,
    period_month,
    scope,
    goal_value,
    unit,
    note,
    updated_by,
    updated_at
  FROM `{gcp_project}.{dataset}.scorecard_goals`
)

SELECT
  a.metric                       AS metric,
  a.period_month                 AS period_month,
  a.scope                        AS scope,
  a.goal_value                   AS goal_value,
  a.unit                         AS unit,
  a.note                         AS note,
  a.updated_by                   AS updated_by,
  a.updated_at                   AS updated_at,
  'app'                          AS goal_source
FROM app a

UNION ALL

-- Only the keys the app has nothing live to say about.
SELECT
  s.metric                       AS metric,
  s.period_month                 AS period_month,
  s.scope                        AS scope,
  s.goal_value                   AS goal_value,
  s.unit                         AS unit,
  s.note                         AS note,
  s.updated_by                   AS updated_by,
  s.updated_at                   AS updated_at,
  'sheet'                        AS goal_source
FROM sheet s
WHERE NOT EXISTS (
  SELECT 1 FROM app a
  WHERE LOWER(TRIM(a.metric)) = LOWER(TRIM(s.metric))
    AND a.period_month = s.period_month
    AND IFNULL(TRIM(a.scope), '') = IFNULL(TRIM(s.scope), '')
)
