-- scorecard_goals_resolved — THE one goal per (metric, month, scope).
--
-- RENAMED from v2_scorecard_goals_resolved 2026-09-22, when the duplicate
-- "v2_" report views were retired. There is now ONE goals pipeline:
--
--     manual-data web app  ──►  Google Sheet  ──►  scorecard_goals_app
--                                                        │
--                                                        ▼
--                                             scorecard_goals_resolved
--                                                        │
--        revenue_vs_goal_report · sales_vs_goal_report · production_vs_goal_report
--
-- Every consumer reads this view. Nothing reads `scorecard_goals_app`
-- directly, so the dedupe rule below is defined in exactly one place.
--
-- ⚠ THE LEGACY LEG IS ON ITS WAY OUT, NOT GONE. `scorecard_goals` was fed by
-- a separate Apps Script from a different Google Sheet
-- (deploy/goals_sheet_to_bigquery.gs, deleted 2026-09-22). It still HOLDS the
-- 68 real sales rep-month goals, which is the only reason its branch survives
-- here: dropping it today would blank the sales-vs-goal tile.
--
-- To finish the retirement, in this order:
--   1. run `importLegacyGoals()` from the manual-data Apps Script — it copies
--      every legacy row into the app's sheet, which is what actually feeds
--      scorecard_goals_app;
--   2. confirm `SELECT COUNT(*) FROM scorecard_goals_resolved WHERE
--      goal_source = 'sheet'` returns 0;
--   3. delete the `sheet` CTE and its UNION branch below; this becomes a thin
--      read of the app table and no consumer changes.
-- Until step 1 runs, DO NOT delete `scorecard_goals` — it is the only copy.
--
-- PRECEDENCE: app first, legacy as fallback. A key present in the app wins; a
-- key absent there falls through, so nothing goes blank mid-migration.
--
-- WHY APPEND-ONLY ON THE APP SIDE: the app never updates or deletes a row, it
-- only adds one, and the newest `updated_at` per key wins. Two people editing
-- the same goal minutes apart cannot lose each other's write the way a
-- read-modify-write would, and every edit stays as history. The cost is this
-- dedupe, which is cheap on a table of goals.
--
-- DELETES ARE TOMBSTONES: the app writes `is_deleted = TRUE` to retract. A
-- tombstone means "the app has nothing to say about this key", so it falls
-- back to the legacy table rather than blanking the goal — a retracted
-- override should restore the previous value, not erase the tile. Once the
-- legacy branch is gone, a tombstone will correctly mean "no goal".
--
-- ⚠ BOTH TABLES ARE HAND-CREATED AND NOT MANAGED BY TERRAFORM, and this view
-- fails to create if either is missing — see docs/reports/scorecard_goals.md
-- for the rebuild DDL.
--
-- Listed in BOTH reports/sales_orders.yaml and reports/work_orders.yaml,
-- because goal views live in both pipelines and each must be able to create
-- its own dependencies. The SQL is identical, so whichever runs second simply
-- replaces an identical view.
-- MUST be listed BEFORE the three *_vs_goal_report views that read it.
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
