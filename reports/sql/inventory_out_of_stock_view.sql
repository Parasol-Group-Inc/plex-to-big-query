-- inventory_out_of_stock_report — parts that are genuinely out of stock,
-- by Vox's own definition (Plex-native source for the Vox Nutrition
-- Scorecard's "OOS" Operational Health tile, replacing the earlier guess
-- at inventory_risk_analysis_report.is_at_risk — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- Jennilyn gave the exact rule (2026-09-01), not a general risk heuristic:
-- "for us to be out of stock, it has to start with 33 for the part
-- number, and it has to have a minimum stock level... if the inventory
-- amount is negative, or we have zero inventory and we have demand...
-- sometimes we make custom parts, those are okay to be negative, because
-- that's just showing us we're in the process of making this part, it's
-- not actually something we stock."
--
-- Three conditions, all required:
--   1. part_no LIKE '33%'
--   2. minimum_inventory_quantity > 0 — DECIDED 2026-09-01: a literal 0
--      counts as "not assigned," not a valid zero threshold (2 of the 7
--      real '33' parts on this tenant have exactly 0.0 here).
--   3. available_vs_total_demand < 0 — on-hand minus demand is negative,
--      which covers BOTH halves of Jennilyn's phrasing (negative inventory,
--      and zero inventory with demand against it).
--   ... EXCLUDING parts whose Product_Type indicates Custom, which are
--      expected to run negative while being made.
--
-- ─────────────────────────────────────────────────────────────────────────
-- REWRITTEN 2026-09-09 — this view no longer computes availability itself.
-- ─────────────────────────────────────────────────────────────────────────
-- It used to derive `on_hand - Sales_v_Release_Allocation.Quantity_Allocated`
-- inline, and it returned ZERO rows for as long as it existed, against a
-- count of 5 on Jennilyn's own sheet. Two separate reasons, both now fixed:
--
--   1. The on-hand filter was `Active = -1`, which matched nothing. Fixed
--      2026-09-04 (Active is 1/0).
--   2. Sales_v_Release_Allocation has 0 rows in PlexTest AND PlexProd and
--      always has. Allocation is a PICKING/STAGING concept — which
--      container is committed to which shipment — and is simply not where
--      Plex keeps demand. The Sep-4 "Sales Order Line Inventory Check"
--      screenshots showed Plex deriving demand from SALES ORDER RELEASES
--      instead, split into Orders / Order Reqd / Job Reqd.
--
-- Availability now comes from inventory_available_to_sell_report, which
-- implements that release-based demand (including BOM-exploded component
-- demand — essential here, because 33xxx blend parts are rarely ordered
-- directly; their demand arrives through the finished goods that consume
-- them). Read that view's header for the demand rules, the
-- Include_In_MRP gate, and what is deliberately excluded.
--
-- available_vs_total_demand is on-hand minus direct order demand minus
-- BOM-exploded component demand. It is now the ONLY sensible reading, and
-- no longer a default chosen on our side:
--
--   * Jennilyn confirmed the formula on 2026-09-09 — "inventory minus
--     required should be the quantity available" — and confirmed the scope
--     is still name-based: "the 33 is the most reliable way", explicitly
--     rejecting a part-type dropdown because it would break the rule.
--   * The "does it include unapproved orders" question is gone: she removed
--     Pending Sales Approval and Deposit Review from Plex's own MRP demand
--     flag the same day, so the demand set is now exactly Pending
--     Fulfillment + Hold. Nothing here has to choose.
--   * The BOM half is not optional for these parts. A 33 blend is almost
--     never ordered directly — without the explosion it shows no demand at
--     all and can never flag.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml, listed
-- AFTER inventory_available_to_sell_report, which this SELECTs from.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per out-of-stock part.

SELECT

  a.part_no                                 AS part_no,
  a.revision                                AS revision,
  a.part_name                               AS part_name,
  a.part_product_type                       AS product_type,
  a.unit                                    AS unit,
  a.minimum_inventory_quantity              AS minimum_inventory_quantity,
  a.on_hand_qty                             AS on_hand_qty,
  a.container_count                         AS container_count,

  -- Demand kept split rather than collapsed to a single number: whether a
  -- part is short because of its own orders or because of what its parents
  -- consume changes what somebody does about it.
  a.order_demand_qty                        AS order_demand_qty,
  a.component_demand_qty                    AS component_demand_qty,
  a.total_demand_qty                        AS total_demand_qty,

  a.available_vs_total_demand               AS quantity_available,

  a.demand_includes_bom_explosion           AS demand_includes_bom_explosion,
  a.no_inventory_on_hand                    AS no_inventory_on_hand

FROM `{gcp_project}.{dataset}.inventory_available_to_sell_report` a

WHERE a.part_no LIKE '33%'
  AND a.minimum_inventory_quantity > 0
  AND a.available_vs_total_demand < 0
  AND COALESCE(a.part_product_type, '') NOT LIKE 'Custom%'
