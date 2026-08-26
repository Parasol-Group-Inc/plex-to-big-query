-- mfg_job_schedule_inventory_availability_report — "Inventory Availability" tab (partial)
--
-- ORIGIN: spreadsheets/mfg_job_schedule_inventory_availability.md. That doc
-- closed out the tab's formulas (% Left, Days on Hand, Reorder Point Days
-- on Hand are all confirmed exact ratios) but found the two inputs the
-- headline columns need have no confirmed Plex source, checked live against
-- every plausible candidate across two research passes:
--   - Avg Daily (usage rate) — Part_v_Part_Planning_Parameters exists but has
--     the wrong columns (MRP/scheduling flags, not a usage rate); 4 other
--     speculative view names don't exist.
--   - Current QTY Available's allocation/committed netting logic — all 5
--     kitting/allocation candidate tables (Part_v_Kitting_Allocation_w,
--     Part_v_Kitting_Production_w, Part_v_Kitting_Production_Log, Part_v_RP,
--     Part_v_Inventory_Allocation) confirmed live to exist with 0 rows —
--     kitting/MRP appears simply unused on this tenant, not a missing join.
-- Both are a data-architect/Vox question, not resolvable by more schema
-- searching — see the doc for the full trail before assuming a formula.
--
-- GRAIN: one row per part. Reuses two already-deployed reports directly
-- (no new extraction) — part_on_hand_inventory_report for Quantity On Hand,
-- purchasing_open_orders_report for On Order. Only the 3 columns confirmed
-- buildable are included: Description, Quantity On Hand, On Order. Reorder
-- Point, Avg Daily, Current QTY Available, % Left, Days on Hand, Days to
-- Reorder Point, and Reorder Point Days on Hand are deliberately NOT built —
-- do not approximate them, per the doc above.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.

SELECT
  oh.part_no                     AS part_no,
  oh.part_name                   AS description,
  oh.on_hand_qty                 AS quantity_on_hand,
  po.on_order_qty                 AS on_order

FROM `{gcp_project}.{dataset}.part_on_hand_inventory_report` oh

LEFT JOIN (
  SELECT
    part_number,
    SUM(SAFE_CAST(qty_ordered AS FLOAT64)) AS on_order_qty
  FROM `{gcp_project}.{dataset}.purchasing_open_orders_report`
  GROUP BY part_number
) po
  ON oh.part_no = po.part_number
