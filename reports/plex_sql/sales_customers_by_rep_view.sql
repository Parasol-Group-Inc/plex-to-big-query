-- sales_customers_by_rep_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_customers_by_rep_view.sql
-- confidence: high
-- plex_views: Sales_v_Order_Salesperson, Sales_v_PO, Plexus_Control_v_Plexus_User, Common_v_Customer
-- notes: Rep-to-customer link is derived from per-order rep assignment (best-criteria assumption, same as BigQuery).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Grain: one row per distinct (rep, customer) pair
SELECT DISTINCT
  u.Plexus_User_No                                      AS sales_rep_key,
  u.First_Name + ' ' + u.Last_Name                      AS sales_rep_name,
  po.Customer_No,
  cust.Name                                             AS customer_name
FROM Sales_v_Order_Salesperson AS os
JOIN Sales_v_PO AS po ON os.PO_Key = po.PO_Key
LEFT JOIN Plexus_Control_v_Plexus_User AS u ON os.Plexus_User_No = u.Plexus_User_No
LEFT JOIN Common_v_Customer AS cust ON po.Customer_No = cust.Customer_No;
