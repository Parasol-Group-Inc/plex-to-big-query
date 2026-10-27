-- mfg_job_schedule_inventory_availability_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/mfg_job_schedule_inventory_availability_view.sql
-- confidence: high
-- plex_views: Part_v_Container, Part_v_Part, Purchasing_v_PO, Purchasing_v_PO_Status, Purchasing_v_Line_Item, Purchasing_v_Release
-- notes: part_on_hand_inventory_report and purchasing_open_orders_report inlined; the open-orders type/supplier joins are omitted (their columns are not used). Only Description, On Hand and On Order are buildable.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part with on-hand stock, plus open PO quantity.
WITH on_hand AS (
  SELECT c.Part_Key AS part_key, SUM(c.Quantity) AS on_hand_qty
  FROM Part_v_Container AS c
  WHERE c.Active = 1
    AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  GROUP BY c.Part_Key
),

part_on_hand AS (
  SELECT p.Part_No AS part_no, p.Name AS part_name, oh.on_hand_qty AS on_hand_qty
  FROM on_hand AS oh
  JOIN Part_v_Part AS p
    ON oh.part_key = p.Part_Key
),

-- open PO quantity per part (open = not cancelled/denied and not received)
po AS (
  SELECT
    p.Part_No         AS part_number,
    SUM(rel.Quantity) AS on_order_qty
  FROM Purchasing_v_PO AS po_h
  LEFT JOIN Purchasing_v_PO_Status AS sts
    ON po_h.PO_Status_Key = sts.PO_Status_Key
  LEFT JOIN Purchasing_v_Line_Item AS li
    ON po_h.PO_Key = li.PO_Key
  LEFT JOIN Purchasing_v_Release AS rel
    ON li.Line_Item_Key = rel.Line_Item_Key
  LEFT JOIN Part_v_Part AS p
    ON li.Part_Key = p.Part_Key
  WHERE COALESCE(sts.Cancelled_Status, 0) = 0
    AND COALESCE(sts.Received, 0) = 0
  GROUP BY p.Part_No
)

SELECT
  oh.part_no           AS part_no,
  oh.part_name         AS description,
  oh.on_hand_qty       AS quantity_on_hand,
  po.on_order_qty      AS on_order
FROM part_on_hand AS oh
LEFT JOIN po AS po
  ON oh.part_no = po.part_number;
