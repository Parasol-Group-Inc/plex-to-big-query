-- ⚠ PROPOSED, NOT DEPLOYED — scorecard sandbox override (2026-09-24).
-- Differs from reports/sql/sales_orders_pending_accounting_approval_view.sql only where marked PROPOSED below.

-- sales_orders_pending_accounting_approval_report — Vox | Orders Pending
-- Approval by Accounting (NetSuite parity, reports-list/sales.md)
--
-- Same shape as sales_orders_pending_approval_view.sql (see that file for
-- the full join notes) — filtered to a different status in the same
-- confirmed workflow.
--
-- STATUS CHOICE — BEST CRITERIA, NOT NETSUITE-CONFIRMED: of the confirmed
-- Sales_v_PO_Status workflow (catalog/plex_catalog_index.md), "Pending
-- Payment Review" (key 2638) is the only accounting-flavored stage — it
-- sits after Released/Pending Fulfillment, before Pending Shipment. This is
-- an inference from the label text, not a NetSuite screenshot. Flag for
-- data-scientist review: confirm this is what "by Accounting" means before
-- trusting this report's row counts.
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
    SAFE_CAST(Breakpoint_Quantity AS FLOAT64)  AS Breakpoint_Quantity
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
  typ.PO_Type                                           AS order_type,

  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS status,

  po.Customer_No,
  cust.Name                                             AS customer_name,

  -- PROPOSED: rep from order Inside_Sales, then customer Assigned_To, then Order_Salesperson.
  COALESCE(CONCAT(ui.First_Name, ' ', ui.Last_Name),
           CONCAT(ua.First_Name, ' ', ua.Last_Name),
           CONCAT(u1.First_Name, ' ', u1.Last_Name))  AS sales_rep_1,
  CONCAT(u2.First_Name, ' ', u2.Last_Name)              AS sales_rep_2,

  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  rel.Quantity                                          AS qty_ordered,
  rel.Quantity_Unit                                     AS qty_unit,

  bp.Price                                              AS price_ea,
  (bp.Price * rel.Quantity)                             AS price_total

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

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
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` ui
  ON SAFE_CAST(po.Inside_Sales AS INT64) = SAFE_CAST(ui.Plexus_User_No AS INT64)
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` ua
  ON SAFE_CAST(cust.Assigned_To AS INT64) = SAFE_CAST(ua.Plexus_User_No AS INT64)
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

-- ⚠ REPOINTED 2026-09-09 — the status this report targeted NO LONGER EXISTS.
-- It filtered `PO_Status_Key = 2638` ("Pending Payment Review"), and Vox cut
-- the sales-order status list from 10 to 7 that day; 2638, 2639 (Pending
-- Shipment) and 2655 (Quote Lost) are gone. The report returned 0 rows and
-- would have returned 0 rows forever, looking exactly like "no orders are
-- pending" rather than "this filter can never match."
--
-- Repointed to **Deposit Review**, which in the new 7-status list is the only
-- accounting-flavoured stage (a deposit is a money gate, and it sits between
-- Pending Sales Approval and Pending Fulfillment). That keeps the report
-- alive, but it is the SECOND inference about what "by Accounting" means —
-- the first one was already flagged for review and never confirmed. **Still
-- needs Jennilyn to confirm.** The `status` column is selected above so
-- whoever reads a row can see which status produced it rather than trusting
-- this comment.
--
-- Matched on the status NAME, not the key, deliberately: a key that vanished
-- is what broke this report, and the same consolidation could renumber again.
-- PROPOSED: Plex now has TWO Deposit Review statuses, "(Initiate Payment
-- Request)" 2587 and "(Bypass Payment Request)" 2656; the exact match found 0.
WHERE UPPER(TRIM(CAST(sts.PO_Status AS STRING))) LIKE 'DEPOSIT REVIEW%'
