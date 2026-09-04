-- inventory_top_quantity_report — parts ranked by on-hand quantity
-- (Plex-native candidate for the Vox Nutrition Scorecard's vw_top_overstock
-- "Top Quantity" category — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- SCOPE LIMIT: quantity ranking only. vw_top_overstock's "Top Value"
-- category needs a $ figure joined to on-hand quantity, which would mean
-- reading raw_Part_v_Snapshot/*_Cost_Sub_Type_Breakdown_History tables
-- extracted by a DIFFERENT pipeline (reports/inventory_snapshot.yaml) — a
-- cross-pipeline raw-table dependency this repo hasn't used before. The
-- existing "thin alias" pattern (see sales_orders_pending_approval_by_rep_view.sql)
-- only chains views within the SAME pipeline's run, backed by main.py's
-- same-run retry-once safety net — that net would NOT cover a raw table
-- owned by a different Cloud Run job on a different schedule. Deliberately
-- deferred rather than shipped with a novel, untested dependency risk —
-- see the migration map doc's Inventory section.
--
-- Thin alias over the already-deployed part_on_hand_inventory_report (same
-- config/pipeline) — MUST stay listed after it in
-- reports/part_on_hand_inventory.yaml's bq_view list.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per part.

SELECT
  part_no,
  part_name,
  part_product_type,
  on_hand_qty,
  container_count,
  RANK() OVER (ORDER BY on_hand_qty DESC) AS qty_rank
FROM `{gcp_project}.{dataset}.part_on_hand_inventory_report`
ORDER BY qty_rank
