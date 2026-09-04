-- shipping_daily_report — packages shipped, orders shipped, and revenue
-- shipped per day (Plex-native candidate for the Vox Nutrition Scorecard's
-- Operations shipping metrics — number of cartons shipped and count of
-- orders shipped — per the Emilio/Jennilyn meeting,
-- meetings-reference/Sep-1/: "they used to show the number of cartons
-- that they shipped every day... you should be able to pull the number of
-- packages shipped, and then a count of the orders that shipped.")
--
-- NEW 2026-09-01. LIVE-CONFIRMED: on this tenant's one real Shipped
-- shipment (SH00001), 17 real Sales_v_Shipper_Container rows (1,000 units
-- each) reconcile exactly to that shipment's 17,000-unit Shipper_Line —
-- COUNT(*) on Shipper_Container is a real "number of cartons" signal here.
--
-- BOOLEAN CONVENTION: Sales_v_Shipper_Status uses 1 = true (confirmed live
-- 2026-09-01) — see shipping_revenue_report.sql's header for the full
-- warning about this NOT being the -1 convention used elsewhere.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml, same
-- Sales_v_Shipper* tables as shipping_revenue_report.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per ship_date.

WITH

shipped_lines AS (
  SELECT
    SAFE_CAST(s.Shipper_Key AS INT64)                     AS Shipper_Key,
    SAFE_CAST(sl.Shipper_Line_Key AS INT64)               AS Shipper_Line_Key,
    SAFE_CAST(sl.Quantity AS FLOAT64)                     AS Quantity,
    SAFE_CAST(sl.Price AS FLOAT64)                        AS Price,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    )                                                     AS ship_date
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Shipper` s
  JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Line` sl
    ON SAFE_CAST(s.Shipper_Key AS INT64) = SAFE_CAST(sl.Shipper_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Status` ss
    ON SAFE_CAST(s.Shipper_Status_Key AS INT64) = SAFE_CAST(ss.Shipper_Status_Key AS INT64)
  WHERE SAFE_CAST(ss.Shipped AS INT64) = 1
),

container_counts AS (
  SELECT
    SAFE_CAST(Shipper_Line_Key AS INT64) AS Shipper_Line_Key,
    COUNT(*)                             AS container_count
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Container`
  GROUP BY Shipper_Line_Key
)

SELECT
  ship_date,
  COUNT(DISTINCT Shipper_Key)                           AS orders_shipped,
  SUM(COALESCE(cc.container_count, 0))                  AS packages_shipped,
  SUM(sl.Quantity)                                      AS units_shipped,
  SUM(sl.Quantity * sl.Price)                           AS revenue_shipped

FROM shipped_lines sl

LEFT JOIN container_counts cc
  ON sl.Shipper_Line_Key = cc.Shipper_Line_Key

WHERE ship_date IS NOT NULL
GROUP BY ship_date
ORDER BY ship_date DESC
