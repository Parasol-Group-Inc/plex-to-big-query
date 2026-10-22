-- quality_cost_by_category_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/quality_cost_by_category_view.sql
-- confidence: high
-- plex_views: Quality_v_Problem_2
-- notes: Upstream quality_nonconformance_report inlined, trimmed to the three columns this roll-up uses.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per (Problem_Category, month).
-- RULE: groups by whatever Problem_Category values exist; no hardcoded Rework/Destruction strings.
WITH nc AS (
  SELECT
    q.Problem_Category              AS problem_category,
    CAST(q.Problem_Date AS date)    AS problem_date,
    q.Cost                          AS cost
  FROM Quality_v_Problem_2 AS q
)

SELECT
  COALESCE(n.problem_category, '(uncategorized)')                          AS problem_category,
  DATEFROMPARTS(YEAR(n.problem_date), MONTH(n.problem_date), 1)            AS problem_month,
  COUNT(*)                                                                 AS nc_count,
  SUM(n.cost)                                                              AS total_cost
FROM nc AS n
WHERE n.problem_date IS NOT NULL
GROUP BY n.problem_category, DATEFROMPARTS(YEAR(n.problem_date), MONTH(n.problem_date), 1)
ORDER BY problem_month DESC, total_cost DESC;
