-- sales_mtd_by_status_change_report — "Sales MTD" as Vox actually defines it:
-- every order line whose order entered "Pending Fulfillment" status for the
-- FIRST time in a given month, dated by that status change (Plex-native
-- source for the Vox Nutrition Scorecard's Sales MTD / Sales YTD /
-- Sales-vs-Goal-by-rep tiles — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-04, per the Emilio/Jennilyn meeting (meetings-reference/Sep-1/).
-- Jennilyn drew a hard line between this and Revenue, which are NOT the same
-- number and must not be built from the same source:
--   "No. So sales month to date is anything that had the status change into
--    pending fulfillment that month to date. So on the sales order statuses,
--    they changed them from quote to pending sales approval to deposit
--    review. Anyways, anything that moved into pending fulfillment status
--    during that month is our sales month to date. So it doesn't matter if
--    it went from pending fulfillment to a different status after. As long
--    as it entered pending fulfillment for the first time that month, it is
--    counted as sales month to date... And it's the date of that status
--    change, not the date of the order or anything else."
-- Revenue, by contrast, is shipped units out of the Shipping module
-- (shipping_revenue_report). Do not conflate the two.
--
-- NO NEW ETL, NO NEW ASSUMPTION: this reuses the exact "Date Approved"
-- mechanism that sales_orders_report has been computing in production since
-- before this scorecard effort started — MIN(Change_Date) over
-- Sales_v_PO_Change WHERE PO_Status_Key = 2073. Key 2073 = "Pending
-- Fulfillment" is CONFIRMED LIVE on this tenant, not inferred: the full Vox
-- order workflow (catalog/plex_catalog_index.md, docs/CHEATSHEET.md) is
--   2585 Pending Sales Approval -> 2587 Deposit Review -> 2586 Released ->
--   2073 Pending Fulfillment -> 2638 Pending Payment Review ->
--   2639 Pending Shipment -> 2074 Closed / 2076 Cancelled
-- Sales_v_PO_Change is already extracted by this same pipeline.
--
-- "FIRST TIME" IS LOAD-BEARING: MIN() over the change log, not a filter on
-- the order's CURRENT status. An order that reached Pending Fulfillment in
-- September and has since moved on to Pending Shipment or Closed still
-- counts in September, exactly as Jennilyn specified. An order that bounces
-- back into Pending Fulfillment a second time is NOT double-counted.
--
-- GRAIN / HEADER-VS-LINE — ONE OPEN QUESTION, DOCUMENTED NOT GUESSED:
-- Jennilyn described this per "order line," but Plex tracks status on the
-- order HEADER (Sales_v_PO.PO_Status_Key); Sales_v_PO_Line_Change carries no
-- status column at all. So every line on an order inherits that order's
-- status-change date. That is the only reading Plex's schema supports, and
-- it's almost certainly what she meant — but it does mean a 12-line order
-- contributes 12 rows all sharing one approval date. Flagged for her to
-- confirm; no alternative is buildable without a line-level status Plex
-- doesn't have.
--
-- SALES REP — BOTH READINGS EXPOSED, NEITHER FORCED: Jennilyn asked to
-- "parse that out by rep... make sure we retain the sales rep associated
-- with it," but Plex allows more than one salesperson per order
-- (Sales_v_Order_Salesperson, one row per rep, with Sort_Order AND a real
-- Commission percentage). Rather than silently pick one rule, this view
-- exposes the primary rep (Sort_Order = 1) as `sales_rep`, the secondary as
-- `sales_rep_2`, and the primary rep's own `commission_pct` — so a
-- commission-weighted split is available downstream without rebuilding the
-- view if she wants that instead of whole-credit-to-rep-1.
--
-- VALUE: same customer base-tier price join used by sales_orders_report and
-- sales_order_value_by_status_report — price x release quantity. Does not
-- include tax or freight (a caveat that applies to every dollar figure in
-- this pipeline, not just this view).
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml. Every raw
-- table below was already being extracted before this view existed.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (PO, PO_Line, Release) that has ever reached Pending
-- Fulfillment, stamped with the month it first got there.

WITH

-- First time each order reached "Pending Fulfillment" (2073).
--
-- DATE CONVERSION PATTERN (used for every date column in this file):
-- Raw date columns can arrive as INT64 nanoseconds (pyodbc datetime ->
-- pandas -> BQ int64), TIMESTAMP (legacy date_col conversion), or STRING
-- (empty-table autodetect). Every branch routes through CAST(col AS STRING)
-- first because that cast is legal from ANY type — a direct
-- SAFE_CAST(INT64 AS DATE) is an invalid cast pair and fails at view-query
-- compile time, not at runtime. 1970-01-01 results are the epoch sentinel.
first_pending_fulfillment AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64) AS PO_Key,
    MIN(
      COALESCE(
        DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Change_Date AS STRING) AS INT64), 0), 1000))),
        NULLIF(SAFE_CAST(CAST(Change_Date AS STRING) AS DATE), DATE '1970-01-01'),
        NULLIF(DATE(SAFE_CAST(CAST(Change_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
      )
    ) AS sales_date
  FROM `{gcp_project}.{dataset}.raw_Sales_v_PO_Change`
  WHERE SAFE_CAST(PO_Status_Key AS INT64) = 2073
  GROUP BY PO_Key
),

-- Primary sales rep (Sort_Order = 1), with their commission share.
rep1 AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64)          AS PO_Key,
    SAFE_CAST(Plexus_User_No AS INT64)  AS Plexus_User_No,
    SAFE_CAST(Commission AS FLOAT64)    AS Commission
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson`
  WHERE SAFE_CAST(Sort_Order AS INT64) = 1
),

-- Secondary sales rep (Sort_Order = 2).
rep2 AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64)          AS PO_Key,
    SAFE_CAST(Plexus_User_No AS INT64)  AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson`
  WHERE SAFE_CAST(Sort_Order AS INT64) = 2
),

-- Base price per customer part (lowest Breakpoint_Quantity tier) — the same
-- tier-selection rule used throughout this pipeline.
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
)

SELECT

  fpf.sales_date                                        AS sales_date,
  DATE_TRUNC(fpf.sales_date, MONTH)                     AS sales_month,
  EXTRACT(YEAR FROM fpf.sales_date)                     AS sales_year,

  po.PO_No                                              AS document_so,
  sts.PO_Status                                         AS current_status,
  typ.PO_Type                                           AS order_type,

  cust.Name                                             AS customer_name,

  CONCAT(u1.First_Name, ' ', u1.Last_Name)              AS sales_rep,
  CONCAT(u2.First_Name, ' ', u2.Last_Name)              AS sales_rep_2,
  rep1.Commission                                       AS commission_pct,

  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,
  pgrp.Part_Product_Group                               AS part_group,

  SAFE_CAST(rel.Quantity AS FLOAT64)                    AS qty_sold,
  bp.Price                                              AS price_ea,
  (bp.Price * SAFE_CAST(rel.Quantity AS FLOAT64))       AS sales_value

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

-- INNER: an order that never reached Pending Fulfillment is not a "sale"
-- under Jennilyn's definition and must not appear at all.
JOIN first_pending_fulfillment fpf
  ON SAFE_CAST(po.PO_Key AS INT64) = fpf.PO_Key

JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON SAFE_CAST(po.PO_Key AS INT64) = SAFE_CAST(pol.PO_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON SAFE_CAST(pol.PO_Line_Key AS INT64) = SAFE_CAST(rel.PO_Line_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(sts.PO_Status_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Type` typ
  ON SAFE_CAST(po.PO_Type_Key AS INT64) = SAFE_CAST(typ.PO_Type_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON SAFE_CAST(po.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)

LEFT JOIN rep1
  ON SAFE_CAST(po.PO_Key AS INT64) = rep1.PO_Key
LEFT JOIN rep2
  ON SAFE_CAST(po.PO_Key AS INT64) = rep2.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u1
  ON rep1.Plexus_User_No = SAFE_CAST(u1.Plexus_User_No AS INT64)
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u2
  ON rep2.Plexus_User_No = SAFE_CAST(u2.Plexus_User_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(pol.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Group` pgrp
  ON SAFE_CAST(p.Part_Group_Key AS INT64) = SAFE_CAST(pgrp.Part_Product_Group_Key AS INT64)

LEFT JOIN base_price bp
  ON SAFE_CAST(pol.Customer_Part_Key AS INT64) = bp.Customer_Part_Key

WHERE fpf.sales_date IS NOT NULL

ORDER BY fpf.sales_date DESC, po.PO_No
