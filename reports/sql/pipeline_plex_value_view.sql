-- pipeline_plex_value_report — the Plex-side half of the Vox Nutrition
-- Scorecard's "Total Pipeline" tile: the dollar value of sales orders
-- sitting in a Quote status or in Pending Sales Approval (see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-04, per the Emilio/Jennilyn meeting (meetings-reference/Sep-1/):
--   "It's a blend of the Monday data and a little bit of the Plex data. So
--    from Plex, we would need the ones that are quotes — the sales orders
--    that have the status quote, and the sales orders that have the status
--    pending sales approval... So it'll be a sum of the Monday data plus the
--    quotes and pending sales approval sales orders."
--
-- ⚠ THIS VIEW IS DELIBERATELY ONLY HALF THE TILE. Total Pipeline =
-- Monday.com opportunities/forecast + THIS. Monday is not a Plex source and
-- this pipeline has no resources for it (the monday-daily-sync Cloud
-- Scheduler job that feeds voxdatalake.VoxScorecardsLive is not managed by
-- this repo's Terraform at all). Whether Monday stays permanently is an
-- open business decision, not something this view can settle — Jennilyn's
-- plan keeps it; this project's working assumption has been that Plex
-- replaces it. Flagged, not resolved. Do not present this figure as
-- "Total Pipeline" on its own.
--
-- "SALES ORDERS THAT HAVE THE STATUS QUOTE" — READ CAREFULLY, THIS IS NOT
-- PLEX'S QUOTE MODULE. She said sales ORDERS with a quote STATUS, which is
-- Sales_v_PO filtered by Sales_v_PO_Status.Is_Quote — a boolean that lives
-- on the order-status lookup this pipeline already extracts. It is NOT
-- Sales_v_Quote / sales_quotes_open_report, which is a separate object with
-- its own workflow (New/Estimating/Quoted/Won/Lost/...). Building this off
-- the Quote module instead would have meant a new extraction of Plex's
-- automotive-flavoured quote-pricing tables (Sales_v_Quote_Price, with its
-- Escalation_Year / IRR / NPV / EBITDA / Die_Cavity_Count fields) that Vox
-- almost certainly does not populate. Reading her words literally keeps
-- this inside already-extracted, already-verified tables and adds zero ETL.
--
-- Status keys CONFIRMED LIVE on this tenant (catalog/plex_catalog_index.md,
-- docs/CHEATSHEET.md): 2585 Pending Sales Approval -> 2587 Deposit Review ->
-- 2586 Released -> 2073 Pending Fulfillment -> 2638 Pending Payment Review
-- -> 2639 Pending Shipment -> 2074 Closed / 2076 Cancelled. `Is_Quote` is a
-- real boolean column on Sales_v_PO_Status; the 1 = true convention on this
-- table was confirmed against real rows 2026-09-01 (do NOT assume the
-- -1 = true convention used on the Part_v_* family here).
--
-- ⚠ OVERLAP WITH WIP: Pending Sales Approval orders counted here are ALSO
-- counted by sales_order_value_by_status_report under its broad WIP reading
-- — see that view's `also_counts_in_pipeline` flag. The same dollars can
-- land in both tiles. Surfaced in both places rather than silently netted,
-- because which tile should own them is Jennilyn's call, not a SQL decision.
--
-- VALUE: same customer base-tier price join used throughout this pipeline —
-- price x release quantity, excluding tax and freight.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml. Every raw
-- table below was already being extracted before this view existed.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (PO, PO_Line, Release) in a pipeline stage.

WITH base_price AS (
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

rep1 AS (
  SELECT
    SAFE_CAST(PO_Key AS INT64)          AS PO_Key,
    SAFE_CAST(Plexus_User_No AS INT64)  AS Plexus_User_No
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Order_Salesperson`
  WHERE SAFE_CAST(Sort_Order AS INT64) = 1
)

SELECT

  -- Which half of the pipeline this row is. Kept as a readable label so the
  -- scorecard can show the two stages separately or summed.
  CASE
    WHEN COALESCE(SAFE_CAST(sts.Is_Quote AS INT64), 0) = 1 THEN 'Quote'
    ELSE 'Pending Sales Approval'
  END                                                   AS pipeline_stage,

  po.PO_No                                              AS document_so,
  SAFE_CAST(po.PO_Status_Key AS INT64)                  AS status_key,
  sts.PO_Status                                         AS so_status,

  -- DATE CONVERSION PATTERN: raw date columns arrive as INT64 nanoseconds,
  -- TIMESTAMP, or STRING depending on load path. Every branch routes through
  -- CAST(col AS STRING) first because that cast is legal from ANY type — a
  -- direct SAFE_CAST(INT64 AS DATE) is an invalid cast pair and fails at
  -- view-creation time. 1970-01-01 = Plex's epoch "no date" sentinel.
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(po.PO_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_created,

  cust.Name                                             AS customer_name,
  CONCAT(u1.First_Name, ' ', u1.Last_Name)              AS sales_rep,

  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,

  SAFE_CAST(rel.Quantity AS FLOAT64)                    AS qty_quoted,
  bp.Price                                              AS price_ea,
  (bp.Price * SAFE_CAST(rel.Quantity AS FLOAT64))       AS pipeline_value

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON SAFE_CAST(po.PO_Key AS INT64) = SAFE_CAST(pol.PO_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON SAFE_CAST(pol.PO_Line_Key AS INT64) = SAFE_CAST(rel.PO_Line_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(sts.PO_Status_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON SAFE_CAST(po.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)

LEFT JOIN rep1
  ON SAFE_CAST(po.PO_Key AS INT64) = rep1.PO_Key
LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u1
  ON rep1.Plexus_User_No = SAFE_CAST(u1.Plexus_User_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(pol.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)

LEFT JOIN base_price bp
  ON SAFE_CAST(pol.Customer_Part_Key AS INT64) = bp.Customer_Part_Key

-- Quote-status orders OR Pending Sales Approval, and never anything already
-- cancelled (a cancelled quote is not pipeline).
WHERE (
        COALESCE(SAFE_CAST(sts.Is_Quote AS INT64), 0) = 1
        OR SAFE_CAST(po.PO_Status_Key AS INT64) = 2585
      )
  AND COALESCE(SAFE_CAST(sts.Cancelled_Status AS INT64), 0) = 0

ORDER BY pipeline_stage, date_created DESC
