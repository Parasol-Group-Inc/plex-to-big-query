-- sales_orders_over_10k_bottles_report — Vox | Orders over 10k bottles
-- (NetSuite parity, reports-list/sales.md)
--
-- BEST-CRITERIA ASSUMPTION, NOT NETSUITE-CONFIRMED: sums Sales_v_Release.
-- Quantity per order regardless of Sales_v_Release.Quantity_Unit — there
-- was no live data available (test tenant's Sales_v_Release rows) to
-- confirm which unit string(s) actually mean "bottles" specifically, vs.
-- cases, cartons, or other order units. This report currently answers
-- "orders with 10k+ total units across all lines," which may overcount if
-- non-bottle units are mixed into the same order. Flag for data-scientist
-- review: confirm the real Quantity_Unit value(s) for bottles before
-- trusting this report, and add a `WHERE rel.Quantity_Unit = '...'` filter
-- once known.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per order (aggregated across lines).

WITH

qty_totals AS (
  SELECT
    pol.PO_Key,
    SUM(SAFE_CAST(rel.Quantity AS FLOAT64)) AS total_quantity,
    STRING_AGG(DISTINCT rel.Quantity_Unit, ', ') AS quantity_units
  FROM `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
    ON pol.PO_Line_Key = rel.PO_Line_Key
  GROUP BY pol.PO_Key
)

SELECT

  po.PO_No                                              AS document_so,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(po.PO_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_created,

  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS status,

  po.Customer_No,
  cust.Name                                             AS customer_name,

  qt.total_quantity,
  qt.quantity_units                                     AS quantity_units_seen

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

JOIN qty_totals qt
  ON po.PO_Key = qt.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON po.PO_Status_Key = sts.PO_Status_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON po.Customer_No = cust.Customer_No

-- 10k-unit threshold — see header note on the unit-basis assumption.
WHERE qt.total_quantity >= 10000
