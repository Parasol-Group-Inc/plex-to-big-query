-- shipping_daily_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/shipping_daily_report_view.sql
-- confidence: high
-- plex_views: Sales_v_Shipper, Sales_v_Shipper_Line, Sales_v_Shipper_Status, Sales_v_Shipper_Container
-- notes: Epoch/date decoding replaced by CAST(Ship_Date AS date); no extraction filters apply.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- One row per ship date, shipped shippers only.
WITH
shipped_lines AS (
  SELECT
    s.Shipper_Key,
    sl.Shipper_Line_Key,
    sl.Quantity,
    sl.Price,
    NULLIF(CAST(s.Ship_Date AS date), '1970-01-01') AS ship_date
  FROM Sales_v_Shipper AS s
  JOIN Sales_v_Shipper_Line AS sl ON s.Shipper_Key = sl.Shipper_Key
  JOIN Sales_v_Shipper_Status AS ss ON s.Shipper_Status_Key = ss.Shipper_Status_Key
  WHERE ss.Shipped = 1
),
container_counts AS (
  SELECT sc.Shipper_Line_Key, COUNT(*) AS container_count
  FROM Sales_v_Shipper_Container AS sc
  GROUP BY sc.Shipper_Line_Key
)
SELECT
  sl.ship_date                                          AS ship_date,
  COUNT(DISTINCT sl.Shipper_Key)                        AS orders_shipped,
  SUM(ISNULL(cc.container_count, 0))                    AS packages_shipped,
  SUM(sl.Quantity)                                      AS units_shipped,
  SUM(sl.Quantity * sl.Price)                           AS revenue_shipped
FROM shipped_lines AS sl
LEFT JOIN container_counts AS cc ON sl.Shipper_Line_Key = cc.Shipper_Line_Key
WHERE sl.ship_date IS NOT NULL
GROUP BY sl.ship_date
ORDER BY sl.ship_date DESC
