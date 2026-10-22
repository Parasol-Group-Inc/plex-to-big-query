-- sales_revenue_run_rate_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_revenue_run_rate_view.sql
-- confidence: high
-- plex_views: Sales_v_Shipper, Sales_v_Shipper_Line, Sales_v_Shipper_Status, Part_v_Part, Part_v_Part_Group
-- notes: Upstream shipping_revenue_report and sales_revenue_summary_report inlined as CTEs; SAFE_DIVIDE becomes NULLIF division with a float cast.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Month-end projection: revenue so far / days elapsed * days in month.
-- Past months are complete (elapsed = days in month); future months have 0 days elapsed.
WITH
shipping_revenue AS (
  -- shipping_revenue_report: one row per shipped shipper line
  SELECT
    NULLIF(CAST(s.Ship_Date AS date), '1970-01-01') AS ship_date,
    pgrp.Part_Group                                 AS part_group,
    sl.Quantity                                     AS quantity_shipped,
    sl.Quantity * sl.Price                          AS shipping_revenue
  FROM Sales_v_Shipper AS s
  JOIN Sales_v_Shipper_Line AS sl ON s.Shipper_Key = sl.Shipper_Key
  JOIN Sales_v_Shipper_Status AS ss ON s.Shipper_Status_Key = ss.Shipper_Status_Key
  LEFT JOIN Part_v_Part AS p ON sl.Part_Key = p.Part_Key
  LEFT JOIN Part_v_Part_Group AS pgrp ON p.Part_Group_Key = pgrp.Part_Group_Key
  WHERE ss.Shipped = 1
),
revenue_summary AS (
  -- sales_revenue_summary_report: month x part group
  SELECT
    DATEFROMPARTS(YEAR(sr.ship_date), MONTH(sr.ship_date), 1) AS revenue_month,
    ISNULL(sr.part_group, '(no group)')                       AS part_group,
    COUNT(*)                                                  AS shipment_line_count,
    SUM(sr.quantity_shipped)                                  AS units_shipped,
    SUM(sr.shipping_revenue)                                  AS shipping_revenue
  FROM shipping_revenue AS sr
  WHERE sr.ship_date IS NOT NULL
  GROUP BY DATEFROMPARTS(YEAR(sr.ship_date), MONTH(sr.ship_date), 1), ISNULL(sr.part_group, '(no group)')
),
monthly AS (
  SELECT
    rs.revenue_month,
    SUM(rs.shipping_revenue)    AS shipping_revenue,
    SUM(rs.units_shipped)       AS units_shipped,
    SUM(rs.shipment_line_count) AS shipment_line_count
  FROM revenue_summary AS rs
  GROUP BY rs.revenue_month
),
calendar AS (
  SELECT
    mo.revenue_month,
    mo.shipping_revenue,
    mo.units_shipped,
    mo.shipment_line_count,
    DAY(EOMONTH(mo.revenue_month)) AS days_in_month,
    CASE
      WHEN mo.revenue_month = DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1) THEN DAY(GETDATE())
      WHEN EOMONTH(mo.revenue_month) < CAST(GETDATE() AS date) THEN DAY(EOMONTH(mo.revenue_month))
      ELSE 0
    END                            AS days_elapsed
  FROM monthly AS mo
)
SELECT
  cal.revenue_month                                                        AS revenue_month,
  cal.shipping_revenue                                                     AS shipping_revenue,
  cal.units_shipped                                                        AS units_shipped,
  cal.shipment_line_count                                                  AS shipment_line_count,
  cal.days_in_month                                                        AS days_in_month,
  cal.days_elapsed                                                         AS days_elapsed,
  CAST(cal.days_elapsed AS float) / NULLIF(cal.days_in_month, 0)           AS pct_into_month,
  cal.shipping_revenue / NULLIF(cal.days_elapsed, 0) * cal.days_in_month   AS run_rate_projection
FROM calendar AS cal
ORDER BY cal.revenue_month DESC
