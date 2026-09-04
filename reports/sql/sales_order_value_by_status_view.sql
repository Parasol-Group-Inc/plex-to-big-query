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
-- ⚠ AMBIGUITY IN THE REQUIREMENT — RESOLVED INTO DATA, NOT GUESSED
-- (documented 2026-09-04). Jennilyn defined WIP two different ways in the
-- same conversation, and they do not produce the same number:
--   BROAD  — "we just need to know if the order line, if it's not a quote,
--             if it's not cancelled or whatever, and if that order line
--             isn't shipped, then it's WIP."
--   STRICT — "it's basically anything that is pending fulfillment really,
--             any order lines that are pending fulfillment."
-- The broad reading additionally sweeps in orders still sitting in Pending
-- Sales Approval (2585) and Deposit Review (2587) — which the strict
-- reading excludes, and which Total Pipeline separately counts.
--
-- This view implements the BROAD reading (every row here qualifies) and
-- exposes `is_pending_fulfillment` so the STRICT number is one filter away.
-- `also_counts_in_pipeline` marks the rows that double-count against Total
-- Pipeline. Nobody has to rebuild anything once she picks — both figures
-- are already queryable, and the gap between them is measurable today.
--
-- Status keys are CONFIRMED LIVE on this tenant, not inferred — the full
-- Vox workflow (catalog/plex_catalog_index.md, docs/CHEATSHEET.md) is
--   2585 Pending Sales Approval -> 2587 Deposit Review -> 2586 Released ->
--   2073 Pending Fulfillment -> 2638 Pending Payment Review ->
--   2639 Pending Shipment -> 2074 Closed / 2076 Cancelled
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml. Uses the
-- Sales_v_Shipper_Line_Release bridge table added 2026-09-01 for the
-- "not yet shipped" check.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (PO, PO_Line, Release) that qualifies as WIP.

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

  -- ── The two readings of "WIP", side by side ────────────────────────────
  -- See the AMBIGUITY block in this file's header. Every row in this view
  -- satisfies the BROAD reading. This flag narrows it to the STRICT one, so
  -- both numbers come out of one view instead of needing a rebuild once
  -- Jennilyn picks:
  --   broad  (as-is)                    -> SUM(wip_value)
  --   strict (literally the status)     -> SUM(wip_value) WHERE is_pending_fulfillment
  (SAFE_CAST(po.PO_Status_Key AS INT64) = 2073)         AS is_pending_fulfillment,

  -- Rows where this is TRUE are ALSO counted in Total Pipeline, which per
  -- the same meeting sums "the quotes and pending sales approval sales
  -- orders." Under the broad reading those dollars appear in both tiles.
  -- Surfaced so the overlap can be measured and netted out, rather than
  -- quietly inflating two tiles at once.
  (SAFE_CAST(po.PO_Status_Key AS INT64) = 2585)         AS also_counts_in_pipeline,

  cust.Name                                             AS customer_name,

  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,

  rel.Release_Key                                       AS release_key,
  SAFE_CAST(rel.Quantity AS FLOAT64)                    AS qty_pending,
  bp.Price                                              AS price_ea,
  (bp.Price * SAFE_CAST(rel.Quantity AS FLOAT64))       AS wip_value

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

LEFT JOIN base_price bp
  ON SAFE_CAST(pol.Customer_Part_Key AS INT64) = bp.Customer_Part_Key

LEFT JOIN release_shipped rs
  ON SAFE_CAST(rel.Release_Key AS INT64) = rs.Release_Key

WHERE COALESCE(SAFE_CAST(sts.Is_Quote AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(sts.Cancelled_Status AS INT64), 0) = 0
  AND rs.Release_Key IS NULL
