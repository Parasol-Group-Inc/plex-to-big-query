-- inventory_avg_daily_usage_report — average daily depletion (usage) rate
-- per part per month (Plex-native candidate for the Vox Nutrition
-- Scorecard's Inventory "Avg. Daily" field — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- Thin alias over the already-deployed inventory_activity_report (same
-- config/pipeline) — MUST stay listed after it in
-- reports/inventory_activity.yaml's bq_view list.
--
-- UNVERIFIED AGAINST REAL DATA: inventory_activity_view.sql's own header
-- notes that Part_v_Cell_Production/Part_v_Cell_Depletion were both EMPTY
-- (schema-confirmed only, no sample values) when that view was built. This
-- average is mathematically correct once real depletion data lands, but
-- has not been checked against a single real value yet — re-verify once
-- this tenant has some.
--
-- DAYS DIVIDED BY — fixed 2026-09-24 (the scorecard sandbox found it): this
-- used to divide EVERY month by its full calendar length, so on the 24th the
-- month in progress was split over 30 days with only 24 days of usage in it,
-- reading ~20% low. Now:
--   * a finished month       -> all its calendar days
--   * the month in progress  -> days elapsed THROUGH TODAY, today included
--                               (EXTRACT(DAY FROM CURRENT_DATE()))
--   * a future month         -> NULL average (nothing has elapsed)
-- Through TODAY, not through the latest depletion date: a day with no usage
-- is a real zero-usage day and belongs in the average. Dividing by the last
-- activity date would inflate an idle part (used on the 3rd, nothing since ->
-- "3 days"), and makes the denominator differ part by part. It is also the
-- same calendar rule sales_revenue_run_rate_report uses for pct_into_month,
-- so the two tiles agree on "how far into the month we are". Calendar days,
-- not working days — same caveat as that tile.
-- Caveat: today counts as a whole day even though the latest ETL run may not
-- hold all of today's activity yet. On the 2nd of the month that can read
-- noticeably low; by mid-month it is noise.
--
-- PER PART, NOT A TOTAL: one row per (part, month), in that part's own unit
-- of measure (`unit`, from Part_v_Part.Unit). Summing avg_daily_usage across
-- parts adds capsules to bottles to kilograms of powder — meaningless. A
-- Looker tile that shows one "Avg. Daily" number must filter to one part (or
-- one unit); this view does not convert units and should not guess.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (part, month).

WITH usage AS (
  SELECT
    a.part_key,
    a.part_number,
    a.part_name,
    a.activity_month,
    a.depleted_quantity,
    CASE
      WHEN a.activity_month = DATE_TRUNC(CURRENT_DATE(), MONTH)
        THEN EXTRACT(DAY FROM CURRENT_DATE())
      WHEN a.activity_month < DATE_TRUNC(CURRENT_DATE(), MONTH)
        THEN DATE_DIFF(DATE_ADD(a.activity_month, INTERVAL 1 MONTH), a.activity_month, DAY)
      ELSE 0
    END                                            AS days_in_period
  FROM `{gcp_project}.{dataset}.inventory_activity_report` a
)

SELECT
  u.part_key,
  u.part_number,
  u.part_name,
  p.Unit                                           AS unit,
  u.activity_month,
  u.depleted_quantity,
  u.days_in_period,
  (u.activity_month = DATE_TRUNC(CURRENT_DATE(), MONTH)) AS is_month_in_progress,
  SAFE_DIVIDE(u.depleted_quantity, NULLIF(u.days_in_period, 0))
                                                   AS avg_daily_usage
FROM usage u
-- Part_v_Part is shared with the sales_orders pipeline — not re-extracted here.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON u.part_key = SAFE_CAST(p.Part_Key AS INT64)
