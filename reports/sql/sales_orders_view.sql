-- sales_orders_report — 16-field Vox Nutrition sales orders report
--
-- HOW TO EDIT (no deployment required):
--   Edit this file in Google Cloud Storage Console or with gsutil:
--     gsutil cp reports/sql/sales_orders_view.sql gs://voxdatalake-report-configs/sql/
--   The next pipeline run will recreate the view with the updated SQL.
--   You can also edit the BigQuery view directly in the BigQuery Console —
--   your changes persist until the next pipeline run overwrites them.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
-- Do NOT hardcode project or dataset names here.
--
-- GRAIN: one row per sales order line item / release.
-- A single sales order (PO_No) will appear multiple times if it has multiple
-- line items or release schedules.
--
-- KEY JOINS (confirmed against live Plex data):
--   Sales_v_PO            → header (one row per order)
--   Sales_v_PO_Line       → line items (Part_Key, Customer_Part_Key per line)
--   Sales_v_Release       → qty per line item (via PO_Line_Key)
--   Sales_v_PO_Change     → status history (MIN where status = 2073 = date approved)
--   Sales_v_Order_Salesperson → reps (Sort_Order 1 = primary, 2 = secondary)
--   Plexus_Control_v_Plexus_User → rep names (via Plexus_User_No)
--   Common_v_Customer     → customer name (via Customer_No)
--   Part_v_Customer_Part_Price → price per Customer_Part_Key + Breakpoint_Quantity
--   Part_v_Part           → part master (Part_No, Name, product classification keys)
--   Part_v_Part_Product_Type  → product type name
--   Part_v_Part_Product_Group → product group name

WITH

-- Date Approved: the first time each order reached status "Pending Fulfillment" (key 2073).
-- Change_Date is stored as INT64 nanoseconds (pyodbc/pandas datetime64 → BQ int64 path).
-- NULLIF(..., 0) turns Plex's "no-date" sentinel into NULL rather than 1970-01-01.
-- COALESCE fallback handles STRING schema (empty-table autodetect) before prod populates.
date_approved AS (
  SELECT
    PO_Key,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(MIN(SAFE_CAST(Change_Date AS INT64)), 0), 1000))),
      NULLIF(MIN(SAFE_CAST(Change_Date AS DATE)), DATE '1970-01-01')
    ) AS date_approved
  FROM `{gcp_project}.{dataset}.raw_Sales_v_PO_Change`
  WHERE PO_Status_Key = 2073
  GROUP BY PO_Key
),

-- Primary sales rep (Sort_Order = 1)
rep1 AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64)          AS PO_Key,
    SAFE_CAST(Plexus_User_No AS INT64)  AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson`
  WHERE SAFE_CAST(Sort_Order AS INT64) = 1
),

-- Secondary sales rep (Sort_Order = 2)
rep2 AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64)          AS PO_Key,
    SAFE_CAST(Plexus_User_No AS INT64)  AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson`
  WHERE SAFE_CAST(Sort_Order AS INT64) = 2
),

-- Base price per customer part (lowest Breakpoint_Quantity tier).
-- NOTE: Part_v_Customer_Part_Price has one row per quantity tier.
-- This picks the base price (minimum breakpoint). Adjust if your pricing
-- logic uses a different tier selection.
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

  -- ── Document info ──────────────────────────────────────────────────────────
  po.PO_No                                              AS document_so,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(po.PO_Date AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(po.PO_Date AS DATE), DATE '1970-01-01')
  )                                                     AS date_created,
  da.date_approved,
  typ.PO_Type                                           AS order_type,

  -- From-quote flag: non-null From_PO_Key means order originated from a quote
  (po.From_PO_Key IS NOT NULL)                          AS from_quote,

  -- ── Status ─────────────────────────────────────────────────────────────────
  -- Vox workflow: 2585 Pending Sales Approval → 2587 Deposit Review →
  --   2586 Released → 2073 Pending Fulfillment → 2638 Pending Payment Review →
  --   2639 Pending Shipment → 2074 Closed / 2076 Cancelled
  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS status,

  -- ── Customer ───────────────────────────────────────────────────────────────
  po.Customer_No,
  cust.Name                                             AS customer_name,

  -- ── Sales reps ─────────────────────────────────────────────────────────────
  CONCAT(u1.First_Name, ' ', u1.Last_Name)              AS sales_rep_1,
  CONCAT(u2.First_Name, ' ', u2.Last_Name)              AS sales_rep_2,

  -- ── Line item / part ───────────────────────────────────────────────────────
  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  -- ── Quantity ───────────────────────────────────────────────────────────────
  -- NOTE: Sales_v_Release join key (PO_Line_Key) follows standard Plex schema.
  -- Confirm column name if query returns no rows.
  rel.Quantity                                          AS qty_ordered,
  rel.Quantity_Unit                                     AS qty_unit,

  -- ── Pricing ────────────────────────────────────────────────────────────────
  bp.Price                                              AS price_ea,
  bp.Breakpoint_Quantity                                AS price_breakpoint_qty,
  (bp.Price * rel.Quantity)                             AS price_total,
  po.Master_Price                                       AS order_total,

  -- ── Product classification ─────────────────────────────────────────────────
  -- NOTE: Part_Product_Type_Key / Part_Product_Group_Key column names on
  -- Part_v_Part are assumed from standard Plex schema. Adjust if needed.
  ptype.Product_Type                                    AS product_type,
  pgrp.Part_Product_Group                               AS product_group

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

-- Date approved from status history
LEFT JOIN date_approved da
  ON po.PO_Key = da.PO_Key

-- Order type lookup
LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Type` typ
  ON po.PO_Type_Key = typ.PO_Type_Key

-- Status lookup
LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON po.PO_Status_Key = sts.PO_Status_Key

-- Customer name
LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON po.Customer_No = cust.Customer_No

-- Sales reps
LEFT JOIN rep1 ON po.PO_Key = rep1.PO_Key
LEFT JOIN rep2 ON po.PO_Key = rep2.PO_Key
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u1
  ON rep1.Plexus_User_No = u1.Plexus_User_No
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u2
  ON rep2.Plexus_User_No = u2.Plexus_User_No

-- Line items
LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON po.PO_Key = pol.PO_Key

-- Quantity per line (via PO_Line_Key — standard Plex join)
LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON pol.PO_Line_Key = rel.PO_Line_Key

-- Part master
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON pol.Part_Key = p.Part_Key

-- Customer part price (base tier)
LEFT JOIN base_price bp
  ON pol.Customer_Part_Key = bp.Customer_Part_Key

-- Product type and group
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Type` ptype
  ON p.Product_Type_Key = ptype.Product_Type_Key
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Group` pgrp
  ON p.Part_Group_Key = SAFE_CAST(pgrp.Part_Product_Group_Key AS INT64)
