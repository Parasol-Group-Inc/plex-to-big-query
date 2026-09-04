-- sales_revenue_summary_report — MTD/YTD shipping revenue rollup by month
-- and part group (Plex-native candidate for the Vox Nutrition Scorecard's
-- "MTD Revenue" / "$28.7M YTD" tiles — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- REBUILT 2026-09-01, SAME DAY AS THE FIRST VERSION — corrected per the
-- Emilio/Jennilyn meeting (meetings-reference/Sep-1/): the first version
-- computed revenue from the Sales module (Sales_v_PO order value). Jennilyn
-- was explicit that's the wrong source: "I think we're gonna want this,
-- the shipping revenue, not the sales revenue... the sales one I think
-- will be less reliable since it will not count in when we like close
-- things short or ship partials." Rebuilt on shipping_revenue_report
-- (Sales_v_Shipper, live-confirmed real data — see that file's header)
-- instead. The NAME is now slightly stale (still says "sales_revenue" even
-- though the source is Shipping) — kept as-is per the 2026-09-01 decision
-- to replace in place rather than leave two similarly-named dead views;
-- rename is a cosmetic cleanup for later.
--
-- Thin alias/rollup over the already-deployed shipping_revenue_report (same
-- config/pipeline) — MUST stay listed after it in
-- reports/sales_orders.yaml's bq_view list. Adds the part-group grouping
-- Jennilyn asked for: "it actually would be pretty nice to have by part
-- group so that I can tell them their percent of revenue by part group."
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (month, part_group). A month/group with no shipments
-- simply won't appear — treat a missing row as $0, not NULL. Sum across
-- part_group for a whole-company total.

SELECT
  DATE_TRUNC(ship_date, MONTH)          AS revenue_month,
  COALESCE(part_group, '(no group)')    AS part_group,
  COUNT(*)                              AS shipment_line_count,
  SUM(quantity_shipped)                 AS units_shipped,
  SUM(shipping_revenue)                 AS shipping_revenue
FROM `{gcp_project}.{dataset}.shipping_revenue_report`
WHERE ship_date IS NOT NULL
GROUP BY revenue_month, part_group
ORDER BY revenue_month DESC, shipping_revenue DESC
