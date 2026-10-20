-- sales_returns_open_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_returns_open_view.sql
-- confidence: high
-- plex_views: Sales_v_Return, Sales_v_Return_Status, Common_v_Customer
-- notes: Mechanical translation; date decoding replaced by CAST(... AS date); no extraction filters apply.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Open returns: excludes closed return statuses 2125 and 2126.
SELECT
  r.Return_No                                        AS document_number,
  NULLIF(CAST(r.Return_Date AS date), '1970-01-01')  AS date_created,
  r.Return_Status_Key                                AS status_key,
  sts.Return_Status                                  AS status,
  r.Customer_No                                      AS customer_no,
  cust.Name                                          AS customer_name,
  r.Order_No                                         AS related_order_no,
  r.Description                                      AS description
FROM Sales_v_Return AS r
LEFT JOIN Sales_v_Return_Status AS sts ON r.Return_Status_Key = sts.Return_Status_Key
LEFT JOIN Common_v_Customer AS cust ON r.Customer_No = cust.Customer_No
WHERE r.Return_Status_Key NOT IN (2125, 2126)
