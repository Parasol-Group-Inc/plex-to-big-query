-- production_vs_goal_report — actual production against target, per work
-- centre group per month, with percent-to-goal (Plex-native source for the
-- Vox Nutrition Scorecard's Encapsulation/Bottling/Labeling "Actual vs. Goal"
-- bars and their "% TO GOAL" tiles — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-04. Reads the maintained `scorecard_goals` table — see
-- revenue_vs_goal_view.sql's header for how that table is fed and why this
-- view fails to create if it's missing. This is the only one of the three
-- goal views that lives on the work_orders pipeline; the other two are on
-- sales_orders. Deliberately split that way so neither pipeline depends on
-- a view the other one creates.
--
-- SCOPE MATCHING IS AN EXACT STRING JOIN on the work centre group, so the
-- sheet must use the value Plex actually emits, not the scorecard's label
-- for it. Confirmed live on this tenant 2026-09-04: 'Bottling' and
-- 'Pre-Weigh' are the only groups with logged production so far.
-- 'Encapsulating' is the Plex group behind the scorecard's "Encapsulation"
-- tile — note the spelling differs from the tile name, which is exactly the
-- kind of mismatch that silently yields a NULL goal. `goal_without_production`
-- below exists to make that visible.
--
-- FULL OUTER JOIN, same reasoning as sales_vs_goal_report: a group with a
-- target and no output yet must still show at 0%, which is the whole point
-- of the tile early in a month. An inner join would hide precisely the case
-- somebody is checking for.
--
-- UNITS, NOT DOLLARS: goal rows for this metric should carry unit='units'.
-- Nothing enforces that — it's a label for readers, not a constraint.
--
-- Thin rollup over the sibling production_monthly_by_workcenter_group_report
-- — MUST stay listed after it in reports/work_orders.yaml's bq_view list.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (month, work centre group).

WITH actual AS (
  SELECT
    production_month,
    workcenter_group,
    SUM(actual_qty) AS actual_qty,
    SUM(scrap_qty)  AS scrap_qty,
    SUM(total_qty)  AS total_qty
  FROM `{gcp_project}.{dataset}.production_monthly_by_workcenter_group_report`
  GROUP BY production_month, workcenter_group
),

goal AS (
  SELECT
    period_month,
    scope           AS workcenter_group,
    SUM(goal_value) AS goal_value,
    ANY_VALUE(note) AS goal_note
  FROM `{gcp_project}.{dataset}.scorecard_goals`
  WHERE LOWER(metric) = 'production'
    AND scope IS NOT NULL
    AND scope != ''
  GROUP BY period_month, scope
)

SELECT
  COALESCE(a.production_month, g.period_month)                  AS production_month,
  COALESCE(a.workcenter_group, g.workcenter_group)              AS workcenter_group,

  COALESCE(a.actual_qty, 0)                                     AS actual_qty,
  COALESCE(a.scrap_qty, 0)                                      AS scrap_qty,
  COALESCE(a.total_qty, 0)                                      AS total_qty,

  g.goal_value,
  SAFE_DIVIDE(COALESCE(a.actual_qty, 0), NULLIF(g.goal_value, 0)) AS pct_to_goal,
  (COALESCE(a.actual_qty, 0) - g.goal_value)                    AS variance_to_goal,

  -- Catches a work centre group spelled differently in the sheet than in Plex.
  (a.workcenter_group IS NULL)                                  AS goal_without_production,
  (g.workcenter_group IS NULL)                                  AS production_without_goal,
  g.goal_note

FROM actual a
FULL OUTER JOIN goal g
  ON a.production_month  = g.period_month
 AND a.workcenter_group  = g.workcenter_group

ORDER BY production_month DESC, workcenter_group
