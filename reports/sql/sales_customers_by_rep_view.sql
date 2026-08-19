-- sales_customers_by_rep_report — Vox | Customer List by Sales Rep
-- (NetSuite parity, reports-list/sales.md)
--
-- BEST-CRITERIA ASSUMPTION, NOT NETSUITE-CONFIRMED: Plex has no standing
-- "customer's assigned rep" field on Common_v_Customer — rep assignment
-- only exists per-order, via Sales_v_Order_Salesperson (already extracted
-- by this pipeline for sales_orders_report's sales_rep_1/2 columns). This
-- report derives "which customers a rep covers" from order history (has the
-- rep been assigned to at least one of this customer's orders), not from a
-- standing account-assignment record. A customer could show up under
-- multiple reps if different orders used different reps. Flag for
-- data-scientist review: confirm whether Plex's per-order rep assignment is
-- an acceptable proxy for a "customer list by rep" report, or whether this
-- needs a different source (e.g. Common_v_Region_Customer_Type.Salesperson,
-- unconfirmed live — see mapping/netsuite-report-mapping.md).
--
-- Rep name resolution: Sales_v_Order_Salesperson.Plexus_User_No →
-- Plexus_Control_v_Plexus_User.First_Name/Last_Name (both already extracted
-- by this pipeline for sales_orders_report).
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per distinct (rep, customer) pair.

SELECT DISTINCT

  u.Plexus_User_No                                      AS sales_rep_key,
  CONCAT(u.First_Name, ' ', u.Last_Name)                AS sales_rep_name,

  po.Customer_No,
  cust.Name                                             AS customer_name

FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson` os

JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO` po
  ON SAFE_CAST(os.PO_Key AS INT64) = po.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u
  ON SAFE_CAST(os.Plexus_User_No AS INT64) = u.Plexus_User_No

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON po.Customer_No = cust.Customer_No
