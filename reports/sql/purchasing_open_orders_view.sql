-- purchasing_open_orders_report — Vox | Open Purchase Orders (NetSuite parity)
--
-- Schema and join keys confirmed via live query against vox.test.odbc.plex.com
-- on 2026-08-10 (empty test tables aside — see below). See
-- docs/NETSUITE_REPORT_BUILD_PLAN.md (#75) for the full confirmation log.
--
-- CONFIRMED LIVE:
--   - Purchasing_v_PO.Supplier_No, PO_Status_Key, PO_Type_Key, PO_Key, PO_No, PO_Date — all exist as named.
--   - Purchasing_v_Line_Item.PO_Key IS the join key back to Purchasing_v_PO (guessed
--     correctly — unlike the Sales side, Purchasing has no separate "PO_Line" view).
--   - Purchasing_v_Release joins to Purchasing_v_Line_Item via Line_Item_Key —
--     Purchasing_v_Release has NO PO_Key column at all, and its own Part_Key
--     column was NULL/0 on every live test row; use Purchasing_v_Line_Item.Part_Key instead.
--   - Purchasing_v_PO_Status status workflow (full list, live 2026-08-10):
--       New (3771), Pending Approval-NS (5559), On Order (3772), Approved (3773),
--       Cancelled (3774, Cancelled_Status=1), Received (3775, Received=1),
--       Denied (5523, Cancelled_Status=1). "Open" = Cancelled_Status=0 AND Received=0
--       — using these boolean flags instead of matching status text/keys, since the
--       label set ("New"/"On Order"/...) has no literal "Closed" status at all,
--       unlike the Sales side's Closed/Cancelled keys.
--   - Common_v_Supplier.Supplier_No / Name confirmed.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- GRAIN: one row per PO line / release, mirroring the sales orders report.
--
-- See the DATE CONVERSION PATTERN comment in reports/sql/sales_orders_view.sql
-- for why every date column below routes through CAST(... AS STRING) first.

SELECT

  -- ── Document info ──────────────────────────────────────────────────────────
  po.PO_No                                              AS document_po,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(po.PO_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_created,
  typ.PO_Type                                           AS order_type,

  -- ── Status ─────────────────────────────────────────────────────────────────
  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS status,

  -- ── Supplier ───────────────────────────────────────────────────────────────
  po.Supplier_No                                        AS supplier_no,
  sup.Name                                              AS supplier_name,

  -- ── Line item / part ───────────────────────────────────────────────────────
  -- Line_Item_No tells apart lines that repeat a part on one PO (audit B11, 2026-10-29).
  SAFE_CAST(li.Line_Item_No AS INT64)                   AS line_no,
  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  -- ── Quantity / due date ────────────────────────────────────────────────────
  rel.Quantity                                          AS qty_ordered,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(rel.Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS due_date,

  -- Appended 2026-10-28. Firmed / Partial (Received releases are excluded
  -- below). A Partial release still shows its full quantity: Plex's
  -- Release view carries no received quantity.
  rel.Release_Status                                    AS release_status

FROM `{gcp_project}.{dataset}.raw_Purchasing_v_PO` po

-- Order type lookup
LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_PO_Type` typ
  ON SAFE_CAST(po.PO_Type_Key AS INT64) = SAFE_CAST(typ.PO_Type_Key AS INT64)

-- Status lookup — filtered to open below via Cancelled_Status/Received flags
LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_PO_Status` sts
  ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(sts.PO_Status_Key AS INT64)

-- Supplier name
LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Supplier` sup
  ON SAFE_CAST(po.Supplier_No AS INT64) = SAFE_CAST(sup.Supplier_No AS INT64)

-- Line items — confirmed join key: Purchasing_v_Line_Item.PO_Key
LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Line_Item` li
  ON SAFE_CAST(po.PO_Key AS INT64) = SAFE_CAST(li.PO_Key AS INT64)

-- Quantity/due date per line — confirmed join key: Line_Item_Key
LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Release` rel
  ON SAFE_CAST(li.Line_Item_Key AS INT64) = SAFE_CAST(rel.Line_Item_Key AS INT64)

-- Part_v_Part is shared with the sales_orders pipeline — not re-extracted here.
-- Confirmed: Line_Item.Part_Key is populated; Release.Part_Key is not — join via Line_Item.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(li.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)

-- "Open" = not cancelled/denied and not yet received, per confirmed status flags.
-- Since 2026-10-28 also per release: an open PO can hold releases already
-- marked Received (9 releases, 35,602 units on 2026-10-28), which are not
-- on order any more.
WHERE COALESCE(SAFE_CAST(sts.Cancelled_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(sts.Received AS INT64), 0) = 0
  AND IFNULL(CAST(rel.Release_Status AS STRING), '') != 'Received'
