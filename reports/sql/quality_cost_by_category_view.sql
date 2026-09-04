-- quality_cost_by_category_report — NC/rework/destruction $ cost rolled up
-- by Problem_Category and month (Plex-native candidate for the Vox
-- Nutrition Scorecard's Quality_Rework "$ Total Cost" and Quality_MatDestr
-- "$ Value" tiles — see score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- DELIBERATELY DOES NOT GUESS the live Problem_Category string values for
-- "Rework" or "Material Destruction" — decided 2026-09-01 rather than
-- hardcode a WHERE clause that could silently return 0 rows if the real
-- strings differ from what the sheet names imply. This groups by whatever
-- Problem_Category values actually exist on this tenant so the data
-- scientist can see the real values live and map them to the scorecard's
-- Rework/Material Destruction categories — at that point this view (or a
-- thin WHERE-filtered view over it) becomes the direct answer.
--
-- Thin alias over the already-deployed quality_nonconformance_report (same
-- config/pipeline) — MUST stay listed after it in
-- reports/quality_nonconformance.yaml's bq_view list (see this repo's
-- retry-once safety net in main.py for why this isn't strictly required,
-- just tidier).
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (Problem_Category, month).

SELECT
  COALESCE(problem_category, '(uncategorized)')   AS problem_category,
  DATE_TRUNC(problem_date, MONTH)                  AS problem_month,
  COUNT(*)                                         AS nc_count,
  SUM(cost)                                        AS total_cost
FROM `{gcp_project}.{dataset}.quality_nonconformance_report`
WHERE problem_date IS NOT NULL
GROUP BY problem_category, problem_month
ORDER BY problem_month DESC, total_cost DESC
