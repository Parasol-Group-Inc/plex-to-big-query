-- sales_order_value_by_status_report — Work In Progress (WIP) dollar value:
-- every order line that's been released/paid for but hasn't shipped yet
-- (Plex-native candidate for the Vox Nutrition Scorecard's "WIP" tile —
-- see score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- REBUILT 2026-09-01, SAME DAY AS THE FIRST VERSION — corrected per the
-- Emilio/Jennilyn meeting (meetings-reference/Sep-1/). The first version
-- used Job_Status ('Production' = WIP). Jennilyn explicitly rejected that:
-- "we don't need the production status... it's basically anything that is
-- pending fulfillment... any order lines that are pending fulfillment...
-- it doesn't matter where in the process it is, doesn't matter if it's in
-- shipping or not... we just need to know if the order line — if it's not
-- a quote, if it's not cancelled or whatever — and if that order line
-- isn't shipped, then it's WIP." No Job/Job_Status involvement at all.
--
-- SCOPE NARROWED: this view now covers WIP only. The original version's
-- separate "is_ready_to_ship"/"Total in Shipping" concept moved to the new
-- shipping_pending_revenue_report, which Jennilyn described as a distinct,
-- Shipper-module-sourced metric ("the revenue value of items that are
-- done, they're in shipping, but they haven't left the building yet") —
-- not the same thing as WIP.
--
-- WIP DEFINITION: an order line is WIP if its PO status is NOT a quote
-- (Sales_v_PO_Status.Is_Quote != 1) AND NOT cancelled (Cancelled_Status
-- != 1) AND no "Shipped" Sales_v_Shipper record exists yet for its
-- Release. BOOLEAN CONVENTION WARNING: Sales_v_PO_Status and
-- Sales_v_Shipper_Status both use 1 = true here, confirmed live 2026-09-01
-- — NOT the -1 = true convention used elsewhere in this pipeline
-- (Part_v_Container.Active, etc.). Checked both tables' real rows before
-- writing this — do not assume one boolean convention applies everywhere.
--
-- VALUE: uses the same customer base-tier price join as
-- sales_orders_report/shipping_revenue_report's fallback — WIP orders
-- generally don't have a Shipper_Line.Price yet (that field appears to
-- populate only once actually shipped), so there's no shipped price to
-- reuse here.
--
-- ✅ THE BROAD/STRICT AMBIGUITY IS SETTLED (2026-09-09). It sat open from
-- 2026-09-04, when Jennilyn had defined WIP two ways in one conversation —
-- broad ("not a quote, not cancelled, not shipped") and strict ("anything
-- that is pending fulfillment"). Neither was quite it. Her ruling:
--
--   "really, it should just be pending fulfillment. I guess hold as well
--    would be WIP because it was sold but it hasn't shipped yet. So it just
--    be those two statuses."
--   "we don't want to count pending sales approval because that's not
--    considered an order yet."
--   "if partials have shipped, we only want the WIP as the value of all of
--    the order lines that haven't shipped yet."
--
-- So: PENDING FULFILLMENT + HOLD, unshipped balance only. This view now
-- implements exactly that in its WHERE clause — SUM(wip_value) is the
-- number, with no flag to filter on and no second reading. The overlap with
-- Total Pipeline is eliminated rather than measured, since neither Quote nor
-- Pending Sales Approval survives the filter.
--
-- ⚠ THE STATUS LIST CHANGED 2026-09-09 — Vox cut it from 10 to 7. Confirmed
-- live that day: Quote (2653), Pending Sales Approval (2585), Deposit Review
-- (2587), Pending Fulfillment (2073), Hold (2075), Closed (2074), Cancelled
-- (2076). **Pending Payment Review (2638), Pending Shipment (2639) and Quote
-- Lost (2655) are gone** ("we did limit our statuses, so there are less
-- statuses now for sales orders because there was way too many"). Any view
-- carrying a hardcoded list of those keys is now silently wrong — this is
-- exactly why the filter below reads Plex's Include_In_MRP flag instead.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml. Uses the
-- Sales_v_Shipper_Line_Release bridge table added 2026-09-01 for the
-- "not yet shipped" check.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (PO, PO_Line, Release) that qualifies as WIP.

WITH

-- SALES ORDER LINE PRICE — the primary price source (added 2026-09-04).
-- Jennilyn, Sep-4: "No, it'll always have a price in there. So it needs to be
-- the line item price." Sales_v_Price is keyed on PO_Line_Key, so this is the
-- price actually agreed on that order line, not a generic list price.
--
-- WHY THIS EXISTS: base_price below joins Part_v_Customer_Part_Price on
-- Customer_Part_Key and matched NOTHING for any of the 7 real Pending
-- Fulfillment orders on this tenant, so WIP and Sales MTD both reported $0
-- across 35,201 real units. It wasn't a broken join — quote-stage orders
-- priced fine through it ($900,975). Those particular parts simply have no
-- customer-price-list row. The order line's own price does not have that gap.
--
-- TIER RULE: prefer Primary_Price, then the lowest Breakpoint_Quantity, then
-- the most recent Effective_Date. Inactive rows are dropped. Same
-- lowest-breakpoint spirit as base_price so the two are comparable.
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
      *,
      ROW_NUMBER() OVER (
        PARTITION BY Customer_Part_Key
        ORDER BY SAFE_CAST(Breakpoint_Quantity AS FLOAT64) ASC
      ) AS rn
    FROM `{gcp_project}.{dataset}.raw_Part_v_Customer_Part_Price`
  )
  WHERE rn = 1
),

release_shipped AS (
  SELECT DISTINCT SAFE_CAST(slr.Release_Key AS INT64) AS Release_Key
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Line_Release` slr
  JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Line` sl
    ON SAFE_CAST(slr.Shipper_Line_Key AS INT64) = SAFE_CAST(sl.Shipper_Line_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper` s
    ON SAFE_CAST(sl.Shipper_Key AS INT64) = SAFE_CAST(s.Shipper_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Status` ss
    ON SAFE_CAST(s.Shipper_Status_Key AS INT64) = SAFE_CAST(ss.Shipper_Status_Key AS INT64)
  WHERE SAFE_CAST(ss.Shipped AS INT64) = 1
)

SELECT

  po.PO_No                                              AS document_so,
  SAFE_CAST(po.PO_Status_Key AS INT64)                  AS status_key,
  sts.PO_Status                                         AS so_status,

  -- ── SETTLED 2026-09-09 — the broad/strict ambiguity is over ────────────
  -- Jennilyn: "really, it should just be pending fulfillment. I guess hold as
  -- well would be WIP because it was sold but it hasn't shipped yet. So it
  -- just be those two statuses." Both flags stay as flags (not filters) so
  -- the split is visible, but the WHERE clause below now admits only those
  -- two statuses, so SUM(wip_value) is THE number — no filter needed and no
  -- second reading to choose between.
  (SAFE_CAST(po.PO_Status_Key AS INT64) = 2073)         AS is_pending_fulfillment,
  (SAFE_CAST(po.PO_Status_Key AS INT64) = 2075)         AS is_on_hold,

  -- The Pipeline overlap is GONE, not merely measurable. Pipeline sums
  -- quotes and pending-sales-approval orders; this view no longer contains
  -- either, so no dollar can appear in both tiles. Kept as a hardcoded FALSE
  -- rather than dropped, because downstream consumers select it by name.
  FALSE                                                 AS also_counts_in_pipeline,

  cust.Name                                             AS customer_name,

  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,

  rel.Release_Key                                       AS release_key,
  -- Net of anything already shipped, per the same conversation: "if partials
  -- have shipped, we only want the WIP as the value of all of the order lines
  -- that haven't shipped yet." The shipped-release exclusion below already
  -- drops a release once a shipment exists against it; this handles the case
  -- where Quantity_Shipped is set without a shipper link, so a part-shipped
  -- release can never contribute more than its remaining balance.
  GREATEST(SAFE_CAST(rel.Quantity AS FLOAT64)
             - COALESCE(SAFE_CAST(rel.Quantity_Shipped AS FLOAT64), 0), 0)
                                                         AS qty_pending,
  COALESCE(lp.Price, bp.Price)                          AS price_ea,
  (lp.Price IS NULL AND bp.Price IS NOT NULL)           AS price_from_fallback_list,
  (COALESCE(lp.Price, bp.Price)
     * GREATEST(SAFE_CAST(rel.Quantity AS FLOAT64)
                  - COALESCE(SAFE_CAST(rel.Quantity_Shipped AS FLOAT64), 0), 0))
                                                         AS wip_value

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON SAFE_CAST(po.PO_Key AS INT64) = SAFE_CAST(pol.PO_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON SAFE_CAST(pol.PO_Line_Key AS INT64) = SAFE_CAST(rel.PO_Line_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(sts.PO_Status_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON SAFE_CAST(po.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(pol.Part_Key AS INT64) = p.Part_Key

LEFT JOIN line_price lp
  ON SAFE_CAST(pol.PO_Line_Key AS INT64) = lp.PO_Line_Key

LEFT JOIN base_price bp
  ON SAFE_CAST(pol.Customer_Part_Key AS INT64) = bp.Customer_Part_Key

LEFT JOIN release_shipped rs
  ON SAFE_CAST(rel.Release_Key AS INT64) = rs.Release_Key

-- ── REWRITTEN 2026-09-09 — WIP is Pending Fulfillment + Hold, nothing else.
-- The old filter was "not a quote, not cancelled", which under Vox's status
-- set also swept in Pending Sales Approval, Deposit Review and Closed. All
-- three are wrong: Jennilyn, 2026-09-09 — "we don't want to count pending
-- sales approval because that's not considered an order yet."
--
-- The gate is Plex's own Include_In_MRP flag rather than a hardcoded status
-- list, and that is now exact: she CHANGED the flags in Plex the same day
-- ("I did change it in Plex because I saw that it was showing demand for
-- deposit review and pending sales approval"). Confirmed live 2026-09-09 —
-- Include_In_MRP is 1 on Pending Fulfillment and Hold, and 0 on Quote,
-- Pending Sales Approval, Deposit Review, Closed and Cancelled. So the flag
-- encodes her definition at the source, and this view tracks it if the
-- statuses change again. Vox also cut the status list from 10 to 7 in the
-- same pass (Pending Payment Review, Pending Shipment and Quote Lost are
-- gone), which a hardcoded list would have silently outlived.
WHERE COALESCE(SAFE_CAST(sts.Include_In_MRP AS INT64), 0) = 1
  AND rs.Release_Key IS NULL
