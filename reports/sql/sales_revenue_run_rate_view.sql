-- sales_revenue_run_rate_report — month-to-date shipping revenue alongside
-- how far through the month we actually are, plus the straight-line
-- projection to month end (Plex-native source for the Vox Nutrition
-- Scorecard's "94% into month" sub-metric and the "MTD Run Rate" tile —
-- see score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-04. This is the one scorecard tile that needed no Plex
-- investigation at all — it's calendar arithmetic over a number we already
-- have. Built now because it was sitting in the "buildable, nobody built
-- it" column and costs nothing.
--
-- Thin rollup over the sibling sales_revenue_summary_report (itself a
-- rollup of shipping_revenue_report) — MUST stay listed AFTER it in
-- reports/sales_orders.yaml's bq_view list.
--
-- REVENUE SOURCE IS SHIPPING, NOT SALES — inherited from
-- sales_revenue_summary_report and correct per the 2026-09-01 meeting:
-- revenue means units that went out the door. Note this is deliberately a
-- DIFFERENT number from sales_mtd_summary_report, which counts orders
-- entering Pending Fulfillment. Both are real; they answer different
-- questions and Jennilyn was explicit that they are not interchangeable.
--
-- pct_into_month is computed against the CALENDAR, matching the existing
-- scorecard's own `pct_into_month` field. It is not a business-day count —
-- if Vox means working days rather than calendar days, this is a one-line
-- change, flagged rather than assumed.
--
-- For a month that has already ended, days_elapsed is the full month and
-- pct_into_month is 100% — so run_rate_projection converges to the actual
-- figure and historical rows stay honest rather than showing a stale
-- part-month projection.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per month that has any shipping revenue.

WITH monthly AS (
  SELECT
    revenue_month,
    SUM(shipping_revenue)   AS shipping_revenue,
    SUM(units_shipped)      AS units_shipped,
    SUM(shipment_line_count) AS shipment_line_count
  FROM `{gcp_project}.{dataset}.sales_revenue_summary_report`
  GROUP BY revenue_month
),

calendar AS (
  SELECT
    revenue_month,
    shipping_revenue,
    units_shipped,
    shipment_line_count,

    -- Last calendar day of that month.
    DATE_SUB(DATE_ADD(revenue_month, INTERVAL 1 MONTH), INTERVAL 1 DAY) AS month_end,

    EXTRACT(DAY FROM DATE_SUB(DATE_ADD(revenue_month, INTERVAL 1 MONTH), INTERVAL 1 DAY))
                                                                        AS days_in_month
  FROM monthly
)

SELECT
  revenue_month,
  shipping_revenue,
  units_shipped,
  shipment_line_count,
  days_in_month,

  -- Days elapsed: the current day-of-month for the month we're in, the whole
  -- month for any month already finished, 0 for a future month.
  CASE
    WHEN revenue_month = DATE_TRUNC(CURRENT_DATE(), MONTH)
      THEN EXTRACT(DAY FROM CURRENT_DATE())
    WHEN month_end < CURRENT_DATE() THEN days_in_month
    ELSE 0
  END                                                   AS days_elapsed,

  SAFE_DIVIDE(
    CASE
      WHEN revenue_month = DATE_TRUNC(CURRENT_DATE(), MONTH)
        THEN EXTRACT(DAY FROM CURRENT_DATE())
      WHEN month_end < CURRENT_DATE() THEN days_in_month
      ELSE 0
    END,
    days_in_month
  )                                                     AS pct_into_month,

  -- Straight-line projection to month end: revenue so far / days elapsed
  -- x days in month. NULL for a future month (nothing to project from).
  SAFE_MULTIPLY(
    SAFE_DIVIDE(
      shipping_revenue,
      NULLIF(
        CASE
          WHEN revenue_month = DATE_TRUNC(CURRENT_DATE(), MONTH)
            THEN EXTRACT(DAY FROM CURRENT_DATE())
          WHEN month_end < CURRENT_DATE() THEN days_in_month
          ELSE 0
        END, 0)
    ),
    days_in_month
  )                                                     AS run_rate_projection

FROM calendar
ORDER BY revenue_month DESC
