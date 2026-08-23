-- purchasing_pending_requisitions_report — Vox | Purchasing | Pending Order Requisitions
-- (NetSuite parity for Saved Transaction Search "Purchasing | Pending Order
-- Requisitions", customsearch2935 — criteria: Status = Requisition:Pending
-- Order, Main Line = true. See reports-list/supply-chain.md.)
--
-- CONFIRMED LIVE against vox.test.odbc.plex.com on 2026-08-13 (schema only —
-- test tenant currently has 0 real rows in Requisition/Requisition_Type/
-- Req_PO_Release, so joins below are UNVERIFIED against real data):
--   - Purchasing_v_Requisition_Status status workflow (full list, live 2026-08-13):
--       New (1565, Approved=0, Allow_PO=0), Approved (1566, Approved=1,
--       Allow_PO=1), Cancelled (1567, Cancelled=1). No status is literally
--       named "Pending Order" — same shape of mismatch as the PO-side report
--       (see purchasing_open_orders_view.sql).
--   - BUSINESS RULE (confirmed with report requester 2026-08-13): "Pending
--     Order" = requisition is Approved (Allow_PO=1) but has NOT yet been
--     turned into a PO release, i.e. no matching row in
--     Purchasing_v_Req_PO_Release for that Requisition_Key.
--   - Purchasing_v_Requisition has BOTH an Item_Key and a Part_Key column.
--     purchasing_open_orders_view.sql's PO-side Line_Item view only has
--     Part_Key populated (Release.Part_Key was NULL/0 on live PO data) — this
--     view assumes Part_Key is the live one here too, but that is NOT yet
--     confirmed since the test tenant has no real Requisition rows. Re-check
--     once prod/real data exists; swap to Item_Key if Part_Key comes back null.
--   - Purchasing_v_Req_PO_Release has no columns beyond Requisition_Key/
--     Line_Item_Key/Release_No — joined on Requisition_Key only, since
--     Purchasing_v_Requisition has no separate line-item table (unlike the PO
--     side, one row here already IS one requisition line).
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- GRAIN: one row per requisition line.
--
-- See the DATE CONVERSION PATTERN comment in reports/sql/sales_orders_view.sql
-- for why every date column below routes through CAST(... AS STRING) first.

SELECT

  -- ── Document info ──────────────────────────────────────────────────────────
  req.Requisition_No                                    AS document_number,
  req.Brief_Description                                 AS description,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(req.Requested_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(req.Requested_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(req.Requested_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_requested,
  typ.Requisition_Type                                  AS order_type,

  -- ── Status ─────────────────────────────────────────────────────────────────
  req.Requisition_Status_Key                            AS status_key,
  sts.Requisition_Status                                AS status,

  -- ── Supplier ───────────────────────────────────────────────────────────────
  req.Supplier_No                                       AS supplier_no,
  sup.Name                                               AS supplier_name,

  -- ── Part ───────────────────────────────────────────────────────────────────
  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  -- ── Quantity / due date ────────────────────────────────────────────────────
  req.Quantity                                          AS qty_requested,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(req.Due_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(req.Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(req.Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS due_date

FROM `{gcp_project}.{dataset}.raw_Purchasing_v_Requisition` req

-- SAFE_CAST both sides on every join below: raw_Purchasing_v_Requisition,
-- raw_Purchasing_v_Requisition_Type, and raw_Purchasing_v_Req_PO_Release are
-- all still 0 rows on both PlexProd and PlexTest (confirmed by the
-- 2026-08-23 production/test runs), so BigQuery autodetected them as
-- all-STRING — while raw_Purchasing_v_Requisition_Status has real rows and
-- is properly typed (INT64). A one-sided join broke view creation outright
-- ("No matching signature for operator = for argument types: STRING,
-- INT64") on the first real scheduled run. SAFE_CAST on both sides is a
-- no-op once these tables get real INT64 data too.

-- Requisition type lookup
LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Requisition_Type` typ
  ON SAFE_CAST(req.Requisition_Type_Key AS INT64) = SAFE_CAST(typ.Requisition_Type_Key AS INT64)

-- Status lookup — filtered to "Approved, not yet released" below
LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Requisition_Status` sts
  ON SAFE_CAST(req.Requisition_Status_Key AS INT64) = SAFE_CAST(sts.Requisition_Status_Key AS INT64)

-- Supplier name — shared table, extracted by the purchasing_open_orders pipeline
LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Supplier` sup
  ON SAFE_CAST(req.Supplier_No AS INT64) = SAFE_CAST(sup.Supplier_No AS INT64)

-- Part number/name — shared table, extracted by the sales_orders pipeline
-- Confirmed for the PO side that Part_Key is the live column; unconfirmed here (see header note).
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(req.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)

-- Has this requisition already become a PO? A matching release row means yes.
LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Req_PO_Release` rel
  ON SAFE_CAST(req.Requisition_Key AS INT64) = SAFE_CAST(rel.Requisition_Key AS INT64)

-- "Pending Order" = approved and buyable, but not yet turned into a PO release.
WHERE COALESCE(SAFE_CAST(sts.Approved AS INT64), 0) = 1
  AND COALESCE(SAFE_CAST(sts.Allow_PO AS INT64), 0) = 1
  AND rel.Requisition_Key IS NULL
