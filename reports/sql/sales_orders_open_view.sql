-- sales_orders_open_report — Vox | Open Sales Orders (NetSuite parity)
--
-- Same fields and raw tables as sales_orders_view.sql (see that file for the
-- full join/date-conversion notes) — this is that view with an "open only"
-- filter added, confirmed with the report requester as status-based
-- (2026-08-10, see docs/NETSUITE_REPORT_BUILD_PLAN.md #76): exclude Closed
-- (2074) and Cancelled (2076), both confirmed in
-- catalog/plex_catalog_index.md's Sales_v_PO_Status workflow table.
--
-- Not re-extracted: reads the same raw_Sales_v_* / raw_Part_v_* / raw_Common_v_*
-- tables the sales_orders pipeline already pulls — this is a second bq_view
-- entry in reports/sales_orders.yaml, not a separate extraction (see
-- main.py's bq_view list support).
--
-- HOW TO EDIT (no deployment required):
--   gcloud storage cp reports/sql/sales_orders_open_view.sql gs://voxdatalake-report-configs/sql/
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
--
-- GRAIN: one row per sales order line item / release, same as sales_orders_report.

WITH

date_approved AS (
  SELECT
    PO_Key,
    MIN(
      COALESCE(
        DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Change_Date AS STRING) AS INT64), 0), 1000))),
        NULLIF(SAFE_CAST(CAST(Change_Date AS STRING) AS DATE), DATE '1970-01-01'),
        NULLIF(DATE(SAFE_CAST(CAST(Change_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
      )
    ) AS date_approved
  FROM `{gcp_project}.{dataset}.raw_Sales_v_PO_Change`
  WHERE PO_Status_Key = 2073
  GROUP BY PO_Key
),

rep1 AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64)          AS PO_Key,
    SAFE_CAST(Plexus_User_No AS INT64)  AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson`
  WHERE SAFE_CAST(Sort_Order AS INT64) = 1
),

rep2 AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64)          AS PO_Key,
    SAFE_CAST(Plexus_User_No AS INT64)  AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson`
  WHERE SAFE_CAST(Sort_Order AS INT64) = 2
),

base_price AS (
  SELECT
    SAFE_CAST(Customer_Part_Key AS INT64)      AS Customer_Part_Key,
    SAFE_CAST(Price AS FLOAT64)                AS Price,
    SAFE_CAST(Breakpoint_Quantity AS FLOAT64)  AS Breakpoint_Quantity,
    Effective_Date,
    Expiration_Date
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
)

SELECT

  po.PO_No                                              AS document_so,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(po.PO_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_created,
  da.date_approved,
  typ.PO_Type                                           AS order_type,

  (po.From_PO_Key IS NOT NULL)                          AS from_quote,

  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS status,

  po.Customer_No,
  cust.Name                                             AS customer_name,

  CONCAT(u1.First_Name, ' ', u1.Last_Name)              AS sales_rep_1,
  CONCAT(u2.First_Name, ' ', u2.Last_Name)              AS sales_rep_2,

  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  rel.Quantity                                          AS qty_ordered,
  rel.Quantity_Unit                                     AS qty_unit,

  bp.Price                                              AS price_ea,
  bp.Breakpoint_Quantity                                AS price_breakpoint_qty,
  (bp.Price * rel.Quantity)                             AS price_total,
  po.Master_Price                                       AS order_total,

  ptype.Product_Type                                    AS product_type,
  pgrp.Part_Product_Group                               AS product_group

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

LEFT JOIN date_approved da
  ON po.PO_Key = da.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Type` typ
  ON po.PO_Type_Key = typ.PO_Type_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON po.PO_Status_Key = sts.PO_Status_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON po.Customer_No = cust.Customer_No

LEFT JOIN rep1 ON po.PO_Key = rep1.PO_Key
LEFT JOIN rep2 ON po.PO_Key = rep2.PO_Key
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u1
  ON rep1.Plexus_User_No = u1.Plexus_User_No
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u2
  ON rep2.Plexus_User_No = u2.Plexus_User_No

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON po.PO_Key = pol.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON pol.PO_Line_Key = rel.PO_Line_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON pol.Part_Key = p.Part_Key

LEFT JOIN base_price bp
  ON pol.Customer_Part_Key = bp.Customer_Part_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Type` ptype
  ON p.Product_Type_Key = ptype.Product_Type_Key
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Group` pgrp
  ON p.Part_Group_Key = SAFE_CAST(pgrp.Part_Product_Group_Key AS INT64)

-- "Open" = not Closed (2074) and not Cancelled (2076), confirmed with the
-- report requester as the intended definition (2026-08-10).
WHERE po.PO_Status_Key NOT IN (2074, 2076)
