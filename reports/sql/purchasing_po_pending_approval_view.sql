-- purchasing_po_pending_approval_report — Vox | Purchase Orders to Approve: Results
-- (NetSuite parity for the "Purchase Orders to Approve: Results" saved search,
-- reports-list/supply-chain.md)
--
-- Same fields and raw tables as purchasing_open_orders_view.sql (see that file
-- for the full join/status-workflow notes) — this is that view with the
-- "Pending Approval-NS" status filter instead of the "open" filter.
--
-- CONFIRMED LIVE (2026-08-10, purchasing_open_orders_view.sql's original
-- confirmation pass): Purchasing_v_PO_Status full workflow includes
-- "Pending Approval-NS" (key 5559) as a distinct status between New (3771)
-- and On Order (3772) — this is Plex's own literal "awaiting approval"
-- state for a supplier PO, so no business-rule guess was needed here.
--
-- Not re-extracted: reads the same raw_Purchasing_v_* / raw_Common_v_Supplier /
-- raw_Part_v_Part tables the purchasing_open_orders pipeline already pulls —
-- this is a second bq_view entry in reports/purchasing_open_orders.yaml.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
--
-- GRAIN: one row per PO line / release, same as purchasing_open_orders_report.

SELECT

  po.PO_No                                              AS document_po,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(po.PO_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_created,
  typ.PO_Type                                           AS order_type,

  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS status,

  po.Supplier_No                                        AS supplier_no,
  sup.Name                                              AS supplier_name,

  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  rel.Quantity                                          AS qty_ordered,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS due_date

FROM `{gcp_project}.{dataset}.raw_Purchasing_v_PO` po

LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_PO_Type` typ
  ON po.PO_Type_Key = typ.PO_Type_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_PO_Status` sts
  ON po.PO_Status_Key = sts.PO_Status_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Supplier` sup
  ON po.Supplier_No = sup.Supplier_No

LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Line_Item` li
  ON po.PO_Key = li.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Release` rel
  ON li.Line_Item_Key = rel.Line_Item_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(li.Part_Key AS INT64) = p.Part_Key

-- "Pending Approval-NS" — Plex's own literal status for this state, no guess.
WHERE po.PO_Status_Key = 5559
