-- purchasing_open_orders_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/purchasing_open_orders_view.sql
-- confidence: high
-- plex_views: Purchasing_v_PO, Purchasing_v_PO_Type, Purchasing_v_PO_Status, Common_v_Supplier, Purchasing_v_Line_Item, Purchasing_v_Release, Part_v_Part
-- notes: Mechanical translation; no extraction-time filters on any source view.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per PO line / release.
-- RULE: open = status is not Cancelled/Denied (Cancelled_Status = 0) and not Received (Received = 0).
SELECT
  po.PO_No                          AS document_po,
  CAST(po.PO_Date AS date)          AS date_created,
  typ.PO_Type                       AS order_type,
  po.PO_Status_Key                  AS status_key,
  sts.PO_Status                     AS status,
  po.Supplier_No                    AS supplier_no,
  sup.Name                          AS supplier_name,
  p.Part_No                         AS part_number,
  p.Name                            AS part_name,
  rel.Quantity                      AS qty_ordered,
  CAST(rel.Due_Date AS date)        AS due_date
FROM Purchasing_v_PO AS po
LEFT JOIN Purchasing_v_PO_Type AS typ
  ON po.PO_Type_Key = typ.PO_Type_Key
LEFT JOIN Purchasing_v_PO_Status AS sts
  ON po.PO_Status_Key = sts.PO_Status_Key
LEFT JOIN Common_v_Supplier AS sup
  ON po.Supplier_No = sup.Supplier_No
LEFT JOIN Purchasing_v_Line_Item AS li     -- join key is PO_Key
  ON po.PO_Key = li.PO_Key
LEFT JOIN Purchasing_v_Release AS rel      -- Release has no PO_Key and no usable Part_Key
  ON li.Line_Item_Key = rel.Line_Item_Key
LEFT JOIN Part_v_Part AS p                 -- part comes from the line item, not the release
  ON li.Part_Key = p.Part_Key
WHERE COALESCE(sts.Cancelled_Status, 0) = 0
  AND COALESCE(sts.Received, 0) = 0;
