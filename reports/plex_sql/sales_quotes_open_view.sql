-- sales_quotes_open_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_quotes_open_view.sql
-- confidence: high
-- plex_views: Sales_v_Quote, Sales_v_Quote_Status, Common_v_Customer
-- notes: Mechanical translation; date decoding replaced by CAST(... AS date); no extraction filters apply.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Open quotes: excludes closed quote statuses 3827-3831.
SELECT
  q.Quote_No                                         AS document_number,
  q.Title                                            AS title,
  NULLIF(CAST(q.Quote_Date AS date), '1970-01-01')   AS date_created,
  NULLIF(CAST(q.Quote_Due_Date AS date), '1970-01-01') AS due_date,
  q.Quote_Status_Key                                 AS status_key,
  sts.Quote_Status                                   AS status,
  q.Customer_No                                      AS customer_no,
  cust.Name                                          AS customer_name
FROM Sales_v_Quote AS q
LEFT JOIN Sales_v_Quote_Status AS sts ON q.Quote_Status_Key = sts.Quote_Status_Key
LEFT JOIN Common_v_Customer AS cust ON q.Customer_No = cust.Customer_No
WHERE q.Quote_Status_Key NOT IN (3827, 3828, 3829, 3830, 3831)
