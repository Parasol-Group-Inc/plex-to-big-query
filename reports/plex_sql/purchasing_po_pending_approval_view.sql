-- purchasing_po_pending_approval_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/purchasing_po_pending_approval_view.sql
-- confidence: high
-- plex_views: Purchasing_v_PO, Purchasing_v_PO_Type, Purchasing_v_PO_Status, Common_v_Supplier, Purchasing_v_Line_Item, Purchasing_v_Release, Part_v_Part
-- notes: Mechanical translation; same shape as open orders but filtered to status key 5559 (Pending Approval-NS).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per PO line / release.
-- RULE: pending approval = PO_Status_Key 5559 ("Pending Approval-NS").
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
LEFT JOIN Purchasing_v_Line_Item AS li
  ON po.PO_Key = li.PO_Key
LEFT JOIN Purchasing_v_Release AS rel
  ON li.Line_Item_Key = rel.Line_Item_Key
LEFT JOIN Part_v_Part AS p
  ON li.Part_Key = p.Part_Key
WHERE po.PO_Status_Key = 5559;
