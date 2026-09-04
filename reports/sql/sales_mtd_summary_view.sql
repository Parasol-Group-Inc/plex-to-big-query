-- sales_mtd_summary_report — Sales MTD / Sales YTD rolled up by month and
-- sales rep, ready to sit straight against the goal table Jennilyn is
-- building (Plex-native source for the Vox Nutrition Scorecard's
-- "Sales MTD", "$28.7M YTD" and "103% to Goal" tiles — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-04, per the Emilio/Jennilyn meeting (meetings-reference/Sep-1/):
--   "So same thing. We'll take that number we just talked about and compare
--    it to their goal, and we'll actually parse that out by rep, too. So
--    when we get our sales month to date, we want to make sure we retain
--    the sales rep associated with it."
--
-- Thin rollup over the sibling sales_mtd_by_status_change_report in this
-- same config — MUST stay listed AFTER it in reports/sales_orders.yaml's
-- bq_view list, or view creation fails on the first pass. (main()'s view
-- loop retries a failed view once after every other view has been tried, so
-- a bad order self-heals within a run — but don't lean on that.)
--
-- MTD vs YTD is a filter on this one view, not two different views:
--   MTD  -> WHERE sales_month = DATE_TRUNC(CURRENT_DATE(), MONTH)
--   YTD  -> WHERE sales_year  = EXTRACT(YEAR FROM CURRENT_DATE())
-- Both then SUM(sales_value). Deliberately NOT hardcoded here so the same
-- view serves the trend charts as well as the two headline tiles.
--
-- YTD HISTORICAL GAP — NOT SOLVED HERE, BY DESIGN: Plex only has data from
-- go-live forward, so YTD out of this view is short by everything that
-- happened earlier in the year. Jennilyn's plan is a static top-up number:
--   "We'll just pull over whatever we get in Plex and then add a static
--    number to it on the date of transfer, and then let it just keep adding
--    from there... we could add in a dummy number right now and then at go
--    live just update it to the prior number."
-- That number belongs in her maintained goal/adjustment table as a real
-- editable row, NOT hardcoded in this SQL where nobody but an engineer
-- could change it. Left out on purpose — see docs/reports/ for the note.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (sales_month, sales_rep). A month/rep with no sales
-- simply won't appear — treat a missing row as $0, not NULL.

SELECT
  sales_month,
  sales_year,
  COALESCE(sales_rep, '(no rep assigned)')  AS sales_rep,

  COUNT(*)                                  AS order_line_count,
  COUNT(DISTINCT document_so)               AS order_count,
  SUM(qty_sold)                             AS qty_sold,
  SUM(sales_value)                          AS sales_value

FROM `{gcp_project}.{dataset}.sales_mtd_by_status_change_report`

WHERE sales_month IS NOT NULL

GROUP BY sales_month, sales_year, sales_rep
ORDER BY sales_month DESC, sales_value DESC
