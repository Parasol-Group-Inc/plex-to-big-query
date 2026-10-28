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
-- FIXED 2026-10-28 (code review):
--   * Grain is now really one row per part number. on-hand was one row per
--     Part_Key and on-order was summed per Part_No and joined by Part_No, so
--     every key of a part repeated the full on-order quantity.
--   * Wrapper keys (extra Part_Keys whose one BOM line points at the stocked
--     key of the same Part_No; the line's Quantity converts units, e.g. 0.001
--     for grams) are converted into the stocked key's unit before summing.
--     Same rule as approaching_msl_view.sql.
--   * Parts on order with no stock are listed (27 were missing): the spine
--     is every key with stock OR an open release.
--   * On order is read from the raw Purchasing tables by Part_Key, with the
--     same open rule as purchasing_open_orders_view.sql (open PO, release not
--     Received). That report has no Part_Key and belongs to another pipeline,
--     so reading it here would tie view creation to its run order.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.

WITH

wrap AS (
  SELECT
    SAFE_CAST(b.Part_Key AS INT64)            AS wrapper_key,
    SAFE_CAST(b.Component_Part_Key AS INT64)  AS root_key,
    MAX(SAFE_CAST(b.Quantity AS FLOAT64))     AS factor
  FROM `{gcp_project}.{dataset}.raw_Part_v_BOM` b
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` pw
    ON SAFE_CAST(pw.Part_Key AS INT64) = SAFE_CAST(b.Part_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` pc
    ON SAFE_CAST(pc.Part_Key AS INT64) = SAFE_CAST(b.Component_Part_Key AS INT64)
  WHERE pw.Part_No = pc.Part_No
    AND SAFE_CAST(pw.Part_Key AS INT64) != SAFE_CAST(pc.Part_Key AS INT64)
    AND COALESCE(SAFE_CAST(b.Active AS INT64), 1) != 0
    AND SAFE_CAST(b.Quantity AS FLOAT64) > 0
  GROUP BY wrapper_key, root_key
),

on_hand AS (
  SELECT
    SAFE_CAST(part_key AS INT64)            AS part_key,
    SUM(SAFE_CAST(on_hand_qty AS FLOAT64))  AS on_hand_qty
  FROM `{gcp_project}.{dataset}.part_on_hand_inventory_report`
  GROUP BY part_key
),

on_order AS (
  SELECT
    SAFE_CAST(li.Part_Key AS INT64)          AS part_key,
    SUM(SAFE_CAST(rel.Quantity AS FLOAT64))  AS on_order_qty
  FROM `{gcp_project}.{dataset}.raw_Purchasing_v_PO` po
  LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_PO_Status` sts
    ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(sts.PO_Status_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Line_Item` li
    ON SAFE_CAST(po.PO_Key AS INT64) = SAFE_CAST(li.PO_Key AS INT64)
  JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Release` rel
    ON SAFE_CAST(li.Line_Item_Key AS INT64) = SAFE_CAST(rel.Line_Item_Key AS INT64)
  WHERE COALESCE(SAFE_CAST(sts.Cancelled_Status AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(sts.Received AS INT64), 0) = 0
    AND IFNULL(CAST(rel.Release_Status AS STRING), '') != 'Received'
  GROUP BY part_key
),

part_keys AS (
  SELECT part_key FROM on_hand
  UNION DISTINCT
  SELECT part_key FROM on_order
)

SELECT
  p.Part_No                                                   AS part_no,
  COALESCE(MAX(IF(w.wrapper_key IS NULL, p.Name, NULL)), MAX(p.Name))
                                                              AS description,
  SUM(COALESCE(oh.on_hand_qty, 0) * COALESCE(w.factor, 1))    AS quantity_on_hand,
  -- NULL when nothing is on order, as before.
  SUM(oo.on_order_qty * COALESCE(w.factor, 1))                AS on_order

FROM part_keys k

JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(p.Part_Key AS INT64) = k.part_key

LEFT JOIN wrap w      ON w.wrapper_key = k.part_key
LEFT JOIN on_hand oh  ON oh.part_key = k.part_key
LEFT JOIN on_order oo ON oo.part_key = k.part_key

GROUP BY p.Part_No
