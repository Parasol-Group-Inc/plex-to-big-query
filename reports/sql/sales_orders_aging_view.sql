-- sales_orders_aging_report — Vox | Report for orders past 14 days old
-- (NetSuite parity, reports-list/sales.md)
--
-- Same shape as sales_orders_open_view.sql — this is that "open" filter
-- (excludes Closed/Cancelled) with an added age threshold.
--
-- BEST-CRITERIA ASSUMPTION, NOT NETSUITE-CONFIRMED: "past 14 days old" is
-- interpreted as "still open, and placed more than 14 days ago" (a staleness/
-- aging report), i.e. PO_Date <= 14 days before the run date. The alternative
-- reading — days since the order's *last status change* rather than its
-- original PO_Date — was not verifiable without a screenshot. Flag for
-- data-scientist review before trusting this report's row counts.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per sales order line item / release.

WITH

rep1 AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64)          AS PO_Key,
    SAFE_CAST(Plexus_User_No AS INT64)  AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson`
  WHERE SAFE_CAST(Sort_Order AS INT64) = 1
),

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

orders AS (
  SELECT
    po.*,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(po.PO_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ) AS order_date
  FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po
)

SELECT

  o.PO_No                                               AS document_so,
  o.order_date                                          AS date_created,
  DATE_DIFF(CURRENT_DATE(), o.order_date, DAY)          AS days_old,
  typ.PO_Type                                           AS order_type,

  o.PO_Status_Key                                       AS status_key,
  sts.PO_Status                                         AS status,

  o.Customer_No,
  cust.Name                                             AS customer_name,

  CONCAT(u1.First_Name, ' ', u1.Last_Name)              AS sales_rep_1,

  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  rel.Quantity                                          AS qty_ordered,
  (bp.Price * rel.Quantity)                             AS price_total

FROM orders o

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Type` typ
  ON o.PO_Type_Key = typ.PO_Type_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON o.PO_Status_Key = sts.PO_Status_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON o.Customer_No = cust.Customer_No

LEFT JOIN rep1 ON o.PO_Key = rep1.PO_Key
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u1
  ON rep1.Plexus_User_No = u1.Plexus_User_No

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON o.PO_Key = pol.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON pol.PO_Line_Key = rel.PO_Line_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON pol.Part_Key = p.Part_Key

LEFT JOIN base_price bp
  ON pol.Customer_Part_Key = bp.Customer_Part_Key

-- "Open" = not Closed (2074) / Cancelled (2076), same definition as
-- sales_orders_open_report. Age threshold is the best-criteria part — see
-- header note.
WHERE o.PO_Status_Key NOT IN (2074, 2076)
  AND o.order_date <= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
