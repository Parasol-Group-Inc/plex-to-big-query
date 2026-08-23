-- sales_returns_open_report — Vox | Open RMA's (NetSuite parity,
-- reports-list/sales.md)
--
-- CONFIRMED LIVE (2026-08-14) Sales_v_Return_Status workflow: New (2122),
-- Received (2124), Closed (2125), Cancelled (2126), Pending Approval (2181),
-- Rejected (2182), Released (2183), Under Review (2184). "Open" = not
-- Closed/Cancelled, same status-exclusion pattern as
-- sales_orders_open_report/purchasing_open_orders_report. The Received/
-- Assigned/Approved/Pending boolean flag columns on this status table were
-- confirmed live to be all-zero across every status (same gap as the
-- Supplier Return side) — this exclusion-list approach avoids relying on them.
--
-- Sales_v_Return had 0 rows on the test tenant at confirmation time — this
-- filter is schema-confirmed only, not verified against real return records.
-- Flag for data-scientist review before trusting row counts.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per customer return (RMA).

SELECT

  r.Return_No                                           AS document_number,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(r.Return_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(r.Return_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(r.Return_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_created,

  r.Return_Status_Key                                   AS status_key,
  sts.Return_Status                                     AS status,

  r.Customer_No                                         AS customer_no,
  cust.Name                                             AS customer_name,

  r.Order_No                                            AS related_order_no,
  r.Description                                         AS description

FROM `{gcp_project}.{dataset}.raw_Sales_v_Return` r

-- SAFE_CAST both sides on every join below and the WHERE filter:
-- raw_Sales_v_Return had 0 rows on the 2026-08-23 first real run, so
-- BigQuery autodetected it all-STRING, while raw_Sales_v_Return_Status and
-- raw_Common_v_Customer both have real data and are properly typed
-- (INT64). A one-sided comparison broke view creation outright ("No
-- matching signature for operator = for argument types: STRING, INT64"),
-- confirmed by the first scheduled run's "table not found" result (the
-- view never actually got created). SAFE_CAST is a no-op once
-- raw_Sales_v_Return gets real INT64 data too.

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Return_Status` sts
  ON SAFE_CAST(r.Return_Status_Key AS INT64) = SAFE_CAST(sts.Return_Status_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON SAFE_CAST(r.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)

-- "Open" = not Closed (2125) / Cancelled (2126) — see header note.
WHERE SAFE_CAST(r.Return_Status_Key AS INT64) NOT IN (2125, 2126)
