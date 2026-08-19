-- sales_revenue_by_rep_report — Vox | Revenue per Sales Rep (NetSuite
-- parity, reports-list/sales.md)
--
-- BEST-CRITERIA ASSUMPTION, NOT NETSUITE-CONFIRMED: revenue is the same
-- computed line total used by sales_orders_over_10k_report (base-tier
-- Part_v_Customer_Part_Price x Sales_v_Release.Quantity) — no tax/freight,
-- and rep assignment is per-order (Sales_v_Order_Salesperson), same caveat
-- as sales_customers_by_rep_report re: no standing customer-rep assignment.
-- An order with no rep row is counted under "Unassigned". Flag for
-- data-scientist review before treating these totals as ground truth.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (rep, order) — sum across reps for a total, or filter
-- to one rep_key for a single rep's book of business.

WITH

base_price AS (
  SELECT
    SAFE_CAST(Customer_Part_Key AS INT64)      AS Customer_Part_Key,
    SAFE_CAST(Price AS FLOAT64)                AS Price
  FROM (
    SELECT
      *,
      ROW_NUMBER() OVER (
        PARTITION BY Customer_Part_Key
        ORDER BY SAFE_CAST(Breakpoint_Quantity AS FLOAT64) ASC
      ) AS rn
    FROM `{gcp_project}.{dataset}.raw_Part_v_Customer_Part_Price`
  )
  WHERE rn = 1
),

order_totals AS (
  SELECT
    pol.PO_Key,
    SUM(bp.Price * SAFE_CAST(rel.Quantity AS FLOAT64)) AS order_total_computed
  FROM `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
    ON pol.PO_Line_Key = rel.PO_Line_Key
  LEFT JOIN base_price bp
    ON pol.Customer_Part_Key = bp.Customer_Part_Key
  GROUP BY pol.PO_Key
),

-- Primary rep only (Sort_Order = 1) — avoids double-counting revenue across
-- primary + secondary rep rows.
rep1 AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64)          AS PO_Key,
    SAFE_CAST(Plexus_User_No AS INT64)  AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson`
  WHERE SAFE_CAST(Sort_Order AS INT64) = 1
)

SELECT

  COALESCE(u.Plexus_User_No, -1)                        AS sales_rep_key,
  COALESCE(CONCAT(u.First_Name, ' ', u.Last_Name), 'Unassigned') AS sales_rep_name,

  po.PO_No                                              AS document_so,
  po.Customer_No,
  cust.Name                                             AS customer_name,
  ot.order_total_computed

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

LEFT JOIN order_totals ot
  ON po.PO_Key = ot.PO_Key

LEFT JOIN rep1
  ON po.PO_Key = rep1.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u
  ON rep1.Plexus_User_No = u.Plexus_User_No

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON po.Customer_No = cust.Customer_No
