-- purchasing_pending_requisitions_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/purchasing_pending_requisitions_view.sql
-- confidence: high
-- plex_views: Purchasing_v_Requisition, Purchasing_v_Requisition_Type, Purchasing_v_Requisition_Status, Common_v_Supplier, Part_v_Part, Purchasing_v_Req_PO_Release
-- notes: Mechanical translation; no extraction-time filters on any source view.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per requisition.
-- RULE: pending = status Approved and Allow_PO, and no PO release exists yet (anti-join on Req_PO_Release).
SELECT
  req.Requisition_No                AS document_number,
  req.Brief_Description             AS description,
  CAST(req.Requested_Date AS date)  AS date_requested,
  typ.Requisition_Type              AS order_type,
  req.Requisition_Status_Key        AS status_key,
  sts.Requisition_Status            AS status,
  req.Supplier_No                   AS supplier_no,
  sup.Name                          AS supplier_name,
  p.Part_No                         AS part_number,
  p.Name                            AS part_name,
  req.Quantity                      AS qty_requested,
  CAST(req.Due_Date AS date)        AS due_date
FROM Purchasing_v_Requisition AS req
LEFT JOIN Purchasing_v_Requisition_Type AS typ
  ON req.Requisition_Type_Key = typ.Requisition_Type_Key
LEFT JOIN Purchasing_v_Requisition_Status AS sts
  ON req.Requisition_Status_Key = sts.Requisition_Status_Key
LEFT JOIN Common_v_Supplier AS sup
  ON req.Supplier_No = sup.Supplier_No
LEFT JOIN Part_v_Part AS p
  ON req.Part_Key = p.Part_Key
LEFT JOIN Purchasing_v_Req_PO_Release AS rel
  ON req.Requisition_Key = rel.Requisition_Key
WHERE COALESCE(sts.Approved, 0) = 1
  AND COALESCE(sts.Allow_PO, 0) = 1
  AND rel.Requisition_Key IS NULL;
