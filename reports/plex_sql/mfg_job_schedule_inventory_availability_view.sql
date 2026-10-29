-- mfg_job_schedule_inventory_availability_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/mfg_job_schedule_inventory_availability_view.sql
-- confidence: high
-- plex_views: Part_v_Container, Part_v_Part, Part_v_BOM, Purchasing_v_PO, Purchasing_v_PO_Status, Purchasing_v_Line_Item, Purchasing_v_Release
-- notes: part_on_hand_inventory_report and purchasing_open_orders_report inlined; the open-orders type/supplier joins are omitted (their columns are not used). Only Description, On Hand and On Order are buildable. 2026-10-28: one row per Part_No, wrapper keys converted, on-order-only parts listed, Received releases excluded.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part number with stock or an open PO release.
WITH wrap AS (
  -- wrapper keys: one BOM line to the stocked key of the same Part_No; Quantity converts units
  SELECT b.Part_Key AS wrapper_key, b.Component_Part_Key AS root_key, MAX(b.Quantity) AS factor
  FROM Part_v_BOM AS b
  JOIN Part_v_Part AS pw ON pw.Part_Key = b.Part_Key
  JOIN Part_v_Part AS pc ON pc.Part_Key = b.Component_Part_Key
  WHERE pw.Part_No = pc.Part_No
    AND pw.Part_Key <> pc.Part_Key
    AND ISNULL(b.Active, 1) <> 0
    AND b.Quantity > 0
  GROUP BY b.Part_Key, b.Component_Part_Key
),

on_hand AS (
  SELECT c.Part_Key AS part_key, SUM(c.Quantity) AS on_hand_qty
  FROM Part_v_Container AS c
  WHERE c.Active = 1
    AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  GROUP BY c.Part_Key
),

-- open PO quantity per part key (open PO, release not Received)
on_order AS (
  SELECT li.Part_Key AS part_key, SUM(rel.Quantity) AS on_order_qty
  FROM Purchasing_v_PO AS po_h
  LEFT JOIN Purchasing_v_PO_Status AS sts
    ON po_h.PO_Status_Key = sts.PO_Status_Key
  JOIN Purchasing_v_Line_Item AS li
    ON po_h.PO_Key = li.PO_Key
  JOIN Purchasing_v_Release AS rel
    ON li.Line_Item_Key = rel.Line_Item_Key
  WHERE COALESCE(sts.Cancelled_Status, 0) = 0
    AND COALESCE(sts.Received, 0) = 0
    AND ISNULL(rel.Release_Status, '') <> 'Received'
  GROUP BY li.Part_Key
),

part_keys AS (
  SELECT oh1.part_key FROM on_hand AS oh1
  UNION
  SELECT oo1.part_key FROM on_order AS oo1
)

SELECT
  p.Part_No                                                         AS part_no,
  ISNULL(MAX(CASE WHEN w.wrapper_key IS NULL THEN p.Name END), MAX(p.Name)) AS description,
  SUM(ISNULL(oh.on_hand_qty, 0) * ISNULL(w.factor, 1))              AS quantity_on_hand,
  SUM(oo.on_order_qty * ISNULL(w.factor, 1))                        AS on_order
FROM part_keys AS k
JOIN Part_v_Part AS p ON p.Part_Key = k.part_key
LEFT JOIN wrap AS w      ON w.wrapper_key = k.part_key
LEFT JOIN on_hand AS oh  ON oh.part_key = k.part_key
LEFT JOIN on_order AS oo ON oo.part_key = k.part_key
GROUP BY p.Part_No;
