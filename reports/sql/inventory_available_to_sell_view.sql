-- inventory_available_to_sell_report — Quantity Available per part, i.e.
-- on-hand inventory minus demand, which is the number Jennilyn asked for
-- directly (email, 2026-09-04): "Traditionally, we use Quantity on Hand -
-- Quantity (Sold, Demand, Allocated, etc) to get this. Sales uses as they
-- sell things, but we also using for reporting OOS."
--
-- NEW 2026-09-09. This view is the BigQuery equivalent of Plex's own
-- "Sales Order Line Inventory Check" screen, which Amber pointed to as the
-- place to see it ("though that is a single part view at a time" — this
-- view is every part at once, which is the whole point of pulling it into
-- BigQuery).
--
-- ─────────────────────────────────────────────────────────────────────────
-- WHY THIS EXISTS / WHAT IT REPLACES
-- ─────────────────────────────────────────────────────────────────────────
-- inventory_out_of_stock_view.sql used to compute availability itself, as
-- `on_hand - Sales_v_Release_Allocation.Quantity_Allocated`, and returned
-- ZERO rows for weeks. Release_Allocation has 0 rows in both PlexTest and
-- PlexProd and always has. The Sep-4 screenshots settled why that was never
-- going to work: allocation is a PICKING/STAGING concept (which container
-- has been committed to which shipment), not demand. Plex's own screen
-- derives demand from SALES ORDER RELEASES, and splits it three ways:
--
--   Orders     — the part is itself on a sales order line
--   Order Reqd — a PARENT finished good is on a sales order line and this
--                part is a component of it (BOM-exploded demand)
--   Job Reqd   — an open job needs the part
--
-- This view implements Orders and Order Reqd. Job Reqd is deliberately NOT
-- included — see "NOT INCLUDED" at the bottom.
--
-- ─────────────────────────────────────────────────────────────────────────
-- WHICH ORDERS COUNT AS DEMAND — Plex's own answer, not a guess
-- ─────────────────────────────────────────────────────────────────────────
-- Sales_v_PO_Status.Include_In_MRP is the flag Plex itself uses to decide
-- whether an order's status creates demand. Confirmed live 2026-09-09
-- against the real 10-status lookup on this tenant:
--
--   Include_In_MRP = 1 : Pending Sales Approval, Deposit Review,
--                        Pending Fulfillment, Pending Payment Review,
--                        Pending Shipment, Hold
--   Include_In_MRP = 0 : Quote, Quote Lost, Closed, Cancelled
--
-- So gating on Include_In_MRP gets quotes, closed and cancelled orders out
-- for free, and it will keep tracking Plex if someone adds a status later —
-- which a hardcoded status-name list would not. NOTE it deliberately does
-- NOT gate on Open_Status: the `Hold` status carries Open_Status = 0 but
-- Include_In_MRP = 1, because goods held are still owed to a customer.
--
-- ✅ SETTLED 2026-09-09, AND AT THE SOURCE. This view originally exposed a
-- second "firm" flavour of every demand column (Include_In_MRP AND Hold = 0)
-- because whether unapproved orders count as demand was a live question — on
-- 2026-09-09 part 93127-00MAXW1-1 carried 10,000 units of Pending Sales
-- Approval demand against 1,500 of Pending Fulfillment.
--
-- Jennilyn answered it and then fixed it upstream the same day: *"I did
-- change it in Plex because I saw that it was showing demand for deposit
-- review and pending sales approval. We don't count those as demand until
-- they're pending fulfillment."* Confirmed live after her change —
-- Include_In_MRP is now **1 on exactly Pending Fulfillment and Hold**, and 0
-- on Quote, Pending Sales Approval, Deposit Review, Closed and Cancelled.
--
-- So the `_firm_` columns are GONE rather than kept for the record: their
-- definition (Hold = 0) would now wrongly drop the `Hold` status, which she
-- explicitly wants counted ("hold as well would be WIP because it was sold
-- but it hasn't shipped yet"). A stale second reading is worse than none.
-- `order_demand_from_held_orders_qty` remains, purely so the Hold portion is
-- visible rather than blended in.
--
-- ─────────────────────────────────────────────────────────────────────────
-- WHY on-hand IS READ FROM ANOTHER VIEW
-- ─────────────────────────────────────────────────────────────────────────
-- on-hand comes from part_on_hand_inventory_report (a permanent view
-- deployed by the part_on_hand_inventory pipeline over the same dataset, so
-- it is live, not a stale copy) rather than re-deriving the container
-- filter here. That filter — Active = 1 plus the explicit OK/Hold/
-- Inspection Required/Hold for Design Order status list — existed in THREE
-- copy-pasted places, which is precisely how the `Active = -1` bug survived
-- in all three at once and made every inventory report read 0 rows while
-- 122 real containers sat there. One definition, one place. The same
-- cross-pipeline pattern is already in use by
-- mfg_job_schedule_inventory_availability_view.sql.
--
-- ─────────────────────────────────────────────────────────────────────────
-- FULL OUTER JOIN, ON PURPOSE
-- ─────────────────────────────────────────────────────────────────────────
-- A part with demand and no inventory is THE out-of-stock case, and a part
-- with inventory and no demand is the healthy case. An inner join would
-- hide the first, which is the only one anybody is paging through a report
-- to find.
--
-- ─────────────────────────────────────────────────────────────────────────
-- NOT INCLUDED (deliberate, so nobody assumes otherwise)
-- ─────────────────────────────────────────────────────────────────────────
--  * "Job Reqd" — open-job component requirements. raw_Part_v_Job /
--    raw_Part_v_Job_Op are owned by the work_orders pipeline and have been
--    0 rows on this tenant every time they have been checked, so the column
--    would be a confidently-wrong zero rather than a number. When jobs
--    carry real rows, this is the place to add it.
--  * Purchase orders inbound. Plex's screen has no such column; "available
--    to sell" is what exists now minus what is owed, not what is on its way.
--    purchasing_open_orders_report already covers on-order separately, and
--    mfg_job_schedule_inventory_availability_report already joins the two.
--  * Any time dimension. Plex's PRP/MRP screens (Amber's other suggestion)
--    show availability projected forward by date; this is a point-in-time
--    figure. Doing it by date needs a demand-by-due-date grain and the
--    snapshot table, which is empty.
--
-- BOOLEAN CONVENTION WARNING: Sales_v_PO_Status flags (Include_In_MRP,
-- Hold, Cancelled_Status) hold 1/0 — confirmed live 2026-09-09 by reading
-- all 10 rows. Part_v_Container.Active is ALSO 1/0. Do not reintroduce -1
-- anywhere in this family of views; see docs/CHEATSHEET.md, whose boolean
-- table was itself the source of the original error.
--
-- SAFE_CAST on both sides of every join: several of these raw tables can
-- legitimately be empty on a given run/tenant, and an empty table's columns
-- come back typed from the ODBC schema rather than inferred from values.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml. MUST be
-- listed BEFORE inventory_out_of_stock_report, which SELECTs from it.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per part that has either on-hand inventory or open demand.

WITH

-- ── Direct sales-order demand ("Orders" on Plex's screen) ────────────────
-- Sales_v_Release is the schedule line under a PO_Line and is where the
-- quantity actually lives: Sales_v_PO_Line has NO quantity column at all
-- (checked 2026-09-09 — it carries pack/min-ship/variance quantities only).
-- Netting Quantity_Shipped off means a fully-shipped release contributes
-- nothing, and GREATEST(..., 0) stops an over-shipped release from
-- subtracting from another release's demand.
order_demand AS (
  SELECT
    SAFE_CAST(l.Part_Key AS INT64) AS part_key,
    SUM(GREATEST(
      SAFE_CAST(r.Quantity AS FLOAT64)
        - COALESCE(SAFE_CAST(r.Quantity_Shipped AS FLOAT64), 0), 0))
                                   AS demand_qty,
    -- The Hold portion, kept visible rather than filtered. Hold means sold
    -- but not yet shipped, so it IS demand — this only separates it out.
    SUM(CASE WHEN SAFE_CAST(ps.Hold AS INT64) = 1 THEN GREATEST(
      SAFE_CAST(r.Quantity AS FLOAT64)
        - COALESCE(SAFE_CAST(r.Quantity_Shipped AS FLOAT64), 0), 0)
      ELSE 0 END)                  AS demand_held_qty,
    COUNT(DISTINCT l.PO_Key)       AS open_order_count

  FROM `{gcp_project}.{dataset}.raw_Sales_v_Release` r

  JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` l
    ON SAFE_CAST(r.PO_Line_Key AS INT64) = SAFE_CAST(l.PO_Line_Key AS INT64)

  JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO` po
    ON SAFE_CAST(l.PO_Key AS INT64) = SAFE_CAST(po.PO_Key AS INT64)

  JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` ps
    ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(ps.PO_Status_Key AS INT64)

  WHERE SAFE_CAST(ps.Include_In_MRP AS INT64) = 1
  GROUP BY part_key
),

-- ── BOM-exploded component demand ("Order Reqd" on Plex's screen) ────────
-- Part_v_Flat_BOM is Plex's PRE-FLATTENED explosion: one row per
-- (top-level Part_Key, Component_Part_Key) with the per-unit Quantity
-- already extended through the intermediate levels, so this is a single
-- multiply-and-sum rather than a recursive CTE.
--
-- ASSUMPTION: that Flat_BOM.Quantity is the quantity of the component per
-- ONE unit of the top-level part. That is the documented meaning of a flat
-- BOM and it is why BOM_Level is carried alongside.
--
-- CHECKED 2026-09-09 against the real extract, as far as this tenant allows:
-- 431 Flat_BOM rows, 137 single-level Part_v_BOM rows, 81 (parent, component)
-- pairs present in both — and the quantities are IDENTICAL on all 81, with
-- **max BOM_Level = 1**. So the two agree wherever they can be compared, and
-- at level 1 per-unit and extended quantities are the same number anyway.
-- **The multi-level case is therefore still unproven** — no Vox BOM on this
-- tenant is deeper than one level yet. Re-run that comparison once one is:
-- if flat quantities stop matching single-level ones on a level-2 component,
-- the flat view is extended (correct for this view) rather than per-level.
-- If component demand ever reads as a suspiciously round multiple of its
-- parent's, this is the first thing to check.
component_demand AS (
  SELECT
    SAFE_CAST(fb.Component_Part_Key AS INT64) AS part_key,
    SUM(od.demand_qty * SAFE_CAST(fb.Quantity AS FLOAT64))
                                              AS demand_qty,
    SUM(od.demand_held_qty * SAFE_CAST(fb.Quantity AS FLOAT64))
                                              AS demand_held_qty,
    COUNT(DISTINCT fb.Part_Key)               AS parent_part_count

  FROM order_demand od

  JOIN `{gcp_project}.{dataset}.raw_Part_v_Flat_BOM` fb
    ON SAFE_CAST(fb.Part_Key AS INT64) = od.part_key

  GROUP BY part_key
),

-- ── On-hand, from the one place that defines it ──────────────────────────
on_hand AS (
  SELECT
    SAFE_CAST(oh.part_key AS INT64) AS part_key,
    oh.part_no,
    oh.revision,
    oh.part_name,
    oh.part_product_type,
    oh.unit,
    oh.on_hand_qty,
    oh.on_hand_weight,
    oh.container_count,
    oh.container_locations
  FROM `{gcp_project}.{dataset}.part_on_hand_inventory_report` oh
),

-- Every part that appears on either side, so the FULL OUTER JOIN below has
-- a single spine to hang both halves off and no part can be dropped.
part_keys AS (
  SELECT part_key FROM on_hand
  UNION DISTINCT
  SELECT part_key FROM order_demand
  UNION DISTINCT
  SELECT part_key FROM component_demand
)

SELECT

  k.part_key                                              AS part_key,
  -- part_no etc. come from the part master rather than from on_hand, so a
  -- part with demand and zero containers is still named rather than NULL.
  p.Part_No                                               AS part_no,
  p.Revision                                              AS revision,
  p.Name                                                  AS part_name,
  pt.Product_Type                                         AS part_product_type,
  p.Unit                                                  AS unit,
  SAFE_CAST(p.Minimum_Inventory_Quantity AS FLOAT64)      AS minimum_inventory_quantity,

  -- ── Inventory side ──
  COALESCE(oh.on_hand_qty, 0)                             AS on_hand_qty,
  oh.on_hand_weight                                       AS on_hand_weight,
  COALESCE(oh.container_count, 0)                         AS container_count,
  oh.container_locations                                  AS container_locations,

  -- ── Demand side, split the way Plex's own screen splits it ──
  COALESCE(od.demand_qty, 0)                              AS order_demand_qty,
  COALESCE(od.demand_held_qty, 0)                         AS order_demand_from_held_orders_qty,
  COALESCE(od.open_order_count, 0)                        AS open_order_count,
  COALESCE(cd.demand_qty, 0)                              AS component_demand_qty,
  COALESCE(cd.demand_held_qty, 0)                         AS component_demand_from_held_orders_qty,
  COALESCE(cd.parent_part_count, 0)                       AS bom_parent_part_count,

  COALESCE(od.demand_qty, 0) + COALESCE(cd.demand_qty, 0) AS total_demand_qty,

  -- ── Availability. Down from four columns to two (2026-09-09): the two
  -- `_firm_` variants are gone now that Plex's own Include_In_MRP flag
  -- encodes Vox's demand rule, so there is no second status reading to
  -- offer. What remains is the one real choice — whether demand includes
  -- what finished goods will consume:
  --
  --   available_vs_orders        — the part's own order lines only.
  --   available_vs_total_demand  — plus BOM-exploded component demand. THIS
  --                                is the out-of-stock number, and the only
  --                                one that works for 33 blend parts, which
  --                                are almost never ordered directly.
  --
  -- Jennilyn's own formula, 2026-09-09: "inventory would be quantity on
  -- hand. Required is going to be our sold and inventory minus required
  -- should be the quantity available."
  COALESCE(oh.on_hand_qty, 0) - COALESCE(od.demand_qty, 0)
                                                          AS available_vs_orders,
  COALESCE(oh.on_hand_qty, 0)
    - (COALESCE(od.demand_qty, 0) + COALESCE(cd.demand_qty, 0))
                                                          AS available_vs_total_demand,

  -- ── Flags, so a reader can see WHY a number looks the way it does
  -- rather than having to reverse-engineer it. Same reasoning as the
  -- goal views' goal_without_sales / goal_without_production flags: an
  -- unmatched or structurally-empty side should announce itself instead of
  -- silently reading as a real zero.
  (oh.part_key IS NULL)                                   AS no_inventory_on_hand,
  (od.part_key IS NULL AND cd.part_key IS NULL)           AS no_open_demand,
  (cd.part_key IS NOT NULL)                               AS demand_includes_bom_explosion

FROM part_keys k

LEFT JOIN on_hand oh          ON k.part_key = oh.part_key
LEFT JOIN order_demand od     ON k.part_key = od.part_key
LEFT JOIN component_demand cd ON k.part_key = cd.part_key

JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON k.part_key = SAFE_CAST(p.Part_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Type` pt
  ON SAFE_CAST(p.Product_Type_Key AS FLOAT64) = SAFE_CAST(pt.Product_Type_Key AS FLOAT64)
