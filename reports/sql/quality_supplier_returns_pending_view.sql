-- quality_supplier_returns_pending_report — Vox | Approve Vendor Return
-- Authorizations (NetSuite parity, reports-list/supply-chain.md)
--
-- CONFIRMED LIVE (2026-08-14) against vox.test.odbc.plex.com — the full
-- Quality_v_Supplier_Return_Status workflow on this tenant:
--   New (2204), Hold (2205), OK to Ship (2206, OK_To_Ship=1),
--   Shipped (2207, Shipped=1), Complete (2208), Cancelled (2209)
--
-- ⚠ BUSINESS-RULE GAP, NOT NETSUITE-CONFIRMED: the schema has Approving/
-- Approved boolean columns on this status table, which is why "Approve
-- Vendor Return Authorizations" looked like a clean flag-based filter — but
-- confirmed live, ALL SIX statuses have Approving=0 and Approved=0. There is
-- no status on this tenant that is ever "awaiting approval" by that flag.
-- This view instead uses a status-EXCLUSION proxy (same open/pending
-- pattern used everywhere else in this repo): anything not yet Shipped
-- (2207), Complete (2208), or Cancelled (2209) — i.e. New/Hold/OK to Ship.
-- Flag for data-scientist review: confirm what "Approve Vendor Return
-- Authorizations" should actually filter to before trusting this report —
-- it may be that approval happens as a permission/workflow step outside
-- this status field entirely (e.g. a NetSuite-side approval step with no
-- Plex-side status change at all).
--
-- Quality_v_Supplier_Return had 0 rows on the test tenant at confirmation
-- time — this filter is schema-confirmed only, not verified against real
-- return records.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per supplier return.

SELECT

  r.Return_No                                           AS document_number,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(r.Add_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(r.Add_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(r.Add_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_created,
  typ.Return_Type                                       AS return_type,

  r.Return_Status_Key                                   AS status_key,
  sts.Return_Status                                     AS status,

  r.Supplier_No                                         AS supplier_no,
  sup.Name                                              AS supplier_name,

  r.Note                                                AS note

FROM `{gcp_project}.{dataset}.raw_Quality_v_Supplier_Return` r

LEFT JOIN `{gcp_project}.{dataset}.raw_Quality_v_Supplier_Return_Status` sts
  ON r.Return_Status_Key = sts.Return_Status_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Quality_v_Supplier_Return_Type` typ
  ON r.Return_Type_Key = typ.Return_Type_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Supplier` sup
  ON r.Supplier_No = sup.Supplier_No

-- Status-exclusion proxy for "pending approval" — see header note.
WHERE r.Return_Status_Key NOT IN (2207, 2208, 2209)
