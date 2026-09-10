-- ═══════════════════════════════════════════════════════════════════════
-- GENERATED FILE — do not hand-edit. Regenerate with the generator noted
-- below after any change to the original.
--
--   original : sales_vs_goal_view.sql
--   generated: v2_sales_vs_goal_view.sql
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
-- v2_sales_vs_goal_report — Sales MTD against each rep's goal, with
-- percent-to-goal (Plex-native source for the Vox Nutrition Scorecard's
-- "$4.8M Goal" and "103% to Goal" tiles — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-04. Reads the maintained `scorecard_goals` table — see
-- revenue_vs_goal_view.sql's header for how that table is fed and why this
-- view fails to create if it's missing.
--
-- SALES ≠ REVENUE. The actual here is sales_mtd_summary_report (order lines
-- entering Pending Fulfillment that month), NOT shipping revenue. Those are
-- two different numbers by design and each has its own goal row —
-- metric='sales' here, metric='revenue' on the sibling view.
--
-- SCOPE MATCHING IS AN EXACT STRING JOIN on the rep name, so the sheet has
-- to spell the rep exactly as sales_mtd_summary_report emits it — including
-- the literal '(no rep assigned)' bucket, which is what unassigned orders
-- collapse into today. A typo produces a NULL goal, not an error, so
-- unmatched goal rows are surfaced explicitly below rather than silently
-- dropped.
--
-- A company-wide sales goal (scope NULL/empty) is also supported: those rows
-- appear with sales_rep '(company-wide)' so a single overall target can sit
-- alongside per-rep ones without a second table.
--
-- FULL OUTER JOIN — DELIBERATE, and different from the revenue view. Two
-- failure modes matter here and both should be visible:
--   * a rep with sales but no goal   -> goal_value NULL
--   * a goal set for a rep with no sales yet -> actual 0, pct_to_goal 0
-- An inner or left join would hide the second case, which is the one that
-- matters at month start when somebody wants to see they're at 0% of target.
--
-- Thin rollup over the sibling sales_mtd_summary_report — MUST stay listed
-- after it in reports/sales_orders.yaml's bq_view list.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (month, sales rep).

WITH actual AS (
  SELECT
    sales_month,
    sales_rep,
    SUM(sales_value)  AS actual_sales,
    SUM(qty_sold)     AS qty_sold,
    SUM(order_count)  AS order_count
  FROM `{gcp_project}.{dataset}.sales_mtd_summary_report`
  GROUP BY sales_month, sales_rep
),

goal AS (
  SELECT
    period_month,
    -- Normalise the company-wide bucket to a readable label so it can sit in
    -- the same column as real rep names.
    IF(scope IS NULL OR scope = '', '(company-wide)', scope) AS sales_rep,
    SUM(goal_value) AS goal_value,
    ANY_VALUE(note) AS goal_note
  FROM `{gcp_project}.{dataset}.v2_scorecard_goals_resolved`
  WHERE LOWER(metric) = 'sales'
  GROUP BY period_month, sales_rep
)

SELECT
  COALESCE(a.sales_month, g.period_month)                    AS sales_month,
  COALESCE(a.sales_rep, g.sales_rep)                         AS sales_rep,

  COALESCE(a.actual_sales, 0)                                AS actual_sales,
  COALESCE(a.qty_sold, 0)                                    AS qty_sold,
  COALESCE(a.order_count, 0)                                 AS order_count,

  g.goal_value,
  SAFE_DIVIDE(COALESCE(a.actual_sales, 0), NULLIF(g.goal_value, 0)) AS pct_to_goal,
  (COALESCE(a.actual_sales, 0) - g.goal_value)               AS variance_to_goal,

  -- Makes a mismatched rep name obvious instead of it quietly reading as 0%.
  (a.sales_rep IS NULL)                                      AS goal_without_sales,
  (g.sales_rep IS NULL)                                      AS sales_without_goal,
  g.goal_note

FROM actual a
FULL OUTER JOIN goal g
  ON a.sales_month = g.period_month
 AND a.sales_rep   = g.sales_rep

ORDER BY sales_month DESC, actual_sales DESC
