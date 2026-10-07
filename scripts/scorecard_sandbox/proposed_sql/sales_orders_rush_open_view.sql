-- sales_orders_rush_open_report — "ATL | RUSH Open SOs" / "Vox | RUSH Open
-- Sos" (NetSuite parity, reports-list/sales.md + reports-list/production.md)
--
-- PREVIOUSLY BLOCKED, now unblocked by two screenshots (2026-08-21):
-- the search criteria (Search Title "ATL | RUSH Open SOs", ID
-- customsearch3967, owner Aaron T Luke) does NOT use a Priority/Rush status
-- field at all — that was the wrong lead (Sales_v_Priority returned 0 rows
-- live, see docs/archive/NETSUITE_PARITY_OPEN_ITEMS.md). The real filter is a text
-- search: `Memo (Main) contains RUSH`. A real order (SO0117746) confirms
-- the convention — its Memo starts literally with "RUSH | New label
-- review...". Plex's `Sales_v_PO.Note` is the equivalent free-text field.
--
-- Same base join shape as sales_orders_open_view.sql (po -> pol -> rel ->
-- part), with a different status exclusion list and the RUSH text filter
-- added.
--
-- STATUS MAPPING: NetSuite excludes "Sales Order:Cancelled, Billed, Closed,
-- Pending Approval". Confirmed Plex equivalents (catalog/plex_catalog_index.md):
-- Cancelled=2076, Closed=2074, Pending Approval~"Pending Sales Approval"=2585.
-- "Billed" has NO confirmed Plex status match — Plex's 9-status workflow has
-- no separate billed/invoiced state; assumed subsumed by Closed (2074) rather
-- than guessed as a distinct exclusion. Flag for data-scientist review if
-- orders are ever seen sitting "Closed" while still unbilled.
--
-- NOT MAPPED (gap, not guessed): NetSuite's "Item:Type is none of
-- Description/Discount/Kit/Markup/Other Charge/Payment/Service/Subtotal" and
-- "Item:Name is not -Not Taxable-" line-level noise filters have no applied
-- Plex equivalent here — same as every other sales_orders_* view in this
-- pipeline, which already join through Sales_v_PO_Line/Part_v_Part without
-- this exclusion. Unconfirmed whether Plex's line schema carries the same
-- non-physical line types at all.
--
-- CONFIRMED (2026-08-21): Sales_v_PO.Note is the RUSH-text field on this
-- tenant per the live Sales_v_PO column list — not yet verified against a
-- real Plex order containing the word "RUSH" (Plex and NetSuite are entered
-- separately; the convention may not carry over 1:1). Flag for
-- data-scientist review before trusting row counts.
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

-- PROPOSED (sandbox only, 2026-10-07): the order-line price.
-- This view priced solely off base_price (Part_v_Customer_Part_Price). Plex
-- has returned 0 rows for that view since the 2026-09-24 tenant cut-back, so
-- the table is frozen with keys that join 0/2,119 to current customer parts
-- and every price_ea/price_total in PlexTest is NULL. The same CTE already
-- lives in sales_mtd_by_status_change / sales_order_value_by_status /
-- pipeline_plex_value, where it prices 80-90% of rows; the 2026-09-04 switch
-- to the line item price was simply never applied here.
-- TIER RULE: prefer Primary_Price, then the lowest Breakpoint_Quantity, then
-- the most recent Effective_Date. Inactive rows are dropped.
line_price AS (
  SELECT
    PO_Line_Key,
    Price
  FROM (
    SELECT
      SAFE_CAST(PO_Line_Key AS INT64)             AS PO_Line_Key,
      SAFE_CAST(Price AS FLOAT64)                 AS Price,
      ROW_NUMBER() OVER (
        PARTITION BY SAFE_CAST(PO_Line_Key AS INT64)
        ORDER BY
          COALESCE(SAFE_CAST(Primary_Price AS INT64), 0) DESC,
          SAFE_CAST(Breakpoint_Quantity AS FLOAT64) ASC,
          SAFE_CAST(CAST(Effective_Date AS STRING) AS STRING) DESC
      ) AS rn
    FROM `{gcp_project}.{dataset}.raw_Sales_v_Price`
    WHERE COALESCE(SAFE_CAST(Active AS INT64), 1) != 0
  )
  WHERE rn = 1
),

base_price AS (
  SELECT
    SAFE_CAST(Customer_Part_Key AS INT64)      AS Customer_Part_Key,
    SAFE_CAST(Price AS FLOAT64)                AS Price
  FROM (
    SELECT
      Customer_Part_Key,
      Price,
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
  typ.PO_Type                                           AS order_type,

  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                          AS status,
  po.Note                                                AS memo,

  po.Customer_No,
  cust.Name                                             AS customer_name,

  CONCAT(u1.First_Name, ' ', u1.Last_Name)              AS sales_rep_1,

  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  rel.Quantity                                          AS qty_ordered,
  rel.Quantity_Unit                                     AS qty_unit,
  (COALESCE(lp.Price, bp.Price) * rel.Quantity)                             AS price_total

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Type` typ
  ON po.PO_Type_Key = typ.PO_Type_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON po.PO_Status_Key = sts.PO_Status_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON po.Customer_No = cust.Customer_No

LEFT JOIN rep1 ON po.PO_Key = rep1.PO_Key
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u1
  ON rep1.Plexus_User_No = u1.Plexus_User_No

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON po.PO_Key = pol.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON pol.PO_Line_Key = rel.PO_Line_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON pol.Part_Key = p.Part_Key

LEFT JOIN base_price bp
  ON pol.Customer_Part_Key = bp.Customer_Part_Key

LEFT JOIN line_price lp
  ON SAFE_CAST(pol.PO_Line_Key AS INT64) = lp.PO_Line_Key

-- "Open" here excludes one more status than sales_orders_open_report's
-- general definition — Pending Sales Approval (2585) is also excluded,
-- matching this search's "is none of ... Pending Approval" criterion.
-- See header note on "Billed" (no Plex equivalent, not excluded here).
WHERE po.PO_Status_Key NOT IN (2074, 2076, 2585)
  AND UPPER(po.Note) LIKE '%RUSH%'
