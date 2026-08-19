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
-- No Quote — i.e. New/Estimating/Quoted/Approved are treated as "open" (a
-- quote still in progress). Flag for data-scientist review: confirm this
-- reading before trusting row counts — "Approved" in particular could
-- arguably belong on either side of "open" depending on what happens next
-- in the Vox quoting workflow.
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

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Quote_Status` sts
  ON q.Quote_Status_Key = sts.Quote_Status_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON q.Customer_No = cust.Customer_No

-- Status-exclusion proxy for "open" — see header note.
WHERE q.Quote_Status_Key NOT IN (3827, 3828, 3830, 3831)
