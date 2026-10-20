-- quality_supplier_returns_pending_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/quality_supplier_returns_pending_view.sql
-- confidence: high
-- plex_views: Quality_v_Supplier_Return, Quality_v_Supplier_Return_Status, Quality_v_Supplier_Return_Type, Common_v_Supplier
-- notes: Mechanical translation; no extraction-time filters (see reports/quality_supplier_returns.yaml).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per supplier return.
-- RULE: pending = Return_Status_Key not in (2207, 2208, 2209), the closed-type statuses.
SELECT
  r.Return_No                       AS document_number,
  CAST(r.Add_Date AS date)          AS date_created,
  typ.Return_Type                   AS return_type,
  r.Return_Status_Key               AS status_key,
  sts.Return_Status                 AS status,
  r.Supplier_No                     AS supplier_no,
  sup.Name                          AS supplier_name,
  r.Note                            AS note
FROM Quality_v_Supplier_Return AS r
LEFT JOIN Quality_v_Supplier_Return_Status AS sts
  ON r.Return_Status_Key = sts.Return_Status_Key
LEFT JOIN Quality_v_Supplier_Return_Type AS typ
  ON r.Return_Type_Key = typ.Return_Type_Key
LEFT JOIN Common_v_Supplier AS sup
  ON r.Supplier_No = sup.Supplier_No
WHERE r.Return_Status_Key NOT IN (2207, 2208, 2209);
