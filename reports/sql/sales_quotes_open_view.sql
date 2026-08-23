-- sales_quotes_open_report — Vox | Open Quotes (NetSuite parity,
-- reports-list/sales.md)
--
-- CONFIRMED LIVE (2026-08-14) Sales_v_Quote_Status workflow: New (3821),
-- Estimating (3825), Quoted (3826), Won (3827), Lost (3828), Approved
-- (3829), Cancelled (3830), No Quote (3831).
--
-- ⚠ BUSINESS-RULE GAP, NOT NETSUITE-CONFIRMED: the schema has a literal
-- Open_Quote boolean column, which is why this looked like an exact-match
-- report — but confirmed live, it is 0 on every one of the 8 statuses above.
-- This view instead uses a status-EXCLUSION proxy (same pattern as
-- sales_orders_open_report): anything not yet Won, Lost, Cancelled, or
-- No Quote is treated as "open."
--
-- DECIDED 2026-08-21 (best-criteria, not NetSuite-confirmed — adjust if
-- reports come out wrong): Approved also excluded, i.e. only
-- New/Estimating/Quoted count as "open." Reasoning: Approved marks the
-- point where the customer decision is made and the quote is moving
-- toward becoming an order — it's no longer awaiting action the way
-- New/Estimating/Quoted are. Revisit if Vox's actual workflow treats
-- Approved quotes as still needing follow-up.
--
-- Sales_v_Quote had 0 rows on the test tenant at confirmation time — this
-- filter is schema-confirmed only, not verified against real quote records.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per quote.

SELECT

  q.Quote_No                                            AS document_number,
  q.Title                                               AS title,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Quote_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Quote_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Quote_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_created,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Quote_Due_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Quote_Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Quote_Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS due_date,

  q.Quote_Status_Key                                    AS status_key,
  sts.Quote_Status                                      AS status,

  q.Customer_No                                         AS customer_no,
  cust.Name                                             AS customer_name

FROM `{gcp_project}.{dataset}.raw_Sales_v_Quote` q

-- SAFE_CAST both sides on every join below and the WHERE filter:
-- raw_Sales_v_Quote had 0 rows on the 2026-08-23 first real run, so
-- BigQuery autodetected it all-STRING, while raw_Sales_v_Quote_Status and
-- raw_Common_v_Customer both have real data and are properly typed
-- (INT64). A one-sided comparison broke view creation outright ("No
-- matching signature for operator = for argument types: STRING, INT64"),
-- confirmed by the first scheduled run's "table not found" result (the
-- view never actually got created). SAFE_CAST is a no-op once
-- raw_Sales_v_Quote gets real INT64 data too.

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Quote_Status` sts
  ON SAFE_CAST(q.Quote_Status_Key AS INT64) = SAFE_CAST(sts.Quote_Status_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON SAFE_CAST(q.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)

-- Status-exclusion proxy for "open" — see header note. 3829 = Approved,
-- excluded per the 2026-08-21 decision above.
WHERE SAFE_CAST(q.Quote_Status_Key AS INT64) NOT IN (3827, 3828, 3829, 3830, 3831)
