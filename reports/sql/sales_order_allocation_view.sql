-- sales_order_allocation_report — "Vox | Allocation Report" (NetSuite
-- parity, reports-list/sales.md — search "Allocation reports")
--
-- ORIGIN: initially "no match found" (bare name only, too generic against a
-- 2,828-view schema). A screenshot of the real saved search
-- (`customsearch_mhi_vox_wo_so_report`, owner Sophia Burr) supplied
-- 2026-08-21 gave real criteria: Type=Work Order, Status IN (Planned,
-- Released), Created From:Type=Sales Order, Created From:Status IN
-- (Partially Fulfilled, Pending Billing, Pending Billing/Partially
-- Fulfilled, Pending Fulfillment) — i.e. jobs generated from a sales order
-- where the order hasn't finished shipping/billing yet.
--
-- JOIN PATH (confirmed live schema, catalog/plex_catalog_index.md +
-- catalog/full_schema_catalog.csv): Sales_v_PO -> Sales_v_PO_Line ->
-- Sales_v_Release (PO_Line_Key) -> Sales_v_Release_Job (Release_Key) ->
-- Part_v_Job (Job_Key). Sales_v_Release_Job is a pure 3-column link table
-- (PCN, Release_Key, Job_Key) — this is the one-hop-removed FK that
-- work_orders.yaml's header note says doesn't exist directly between
-- Part_v_Work_Order and Part_v_Job; it exists through Release instead.
--
-- STATUS MAPPING — DECIDED 2026-08-21 (open-status proxy, same call as
-- sales_orders_open_report/sales_quotes_open_report/sales_returns_open_report):
-- of NetSuite's 4 sales-order statuses in this filter, only "Pending
-- Fulfillment" (Sales_v_PO_Status key 2073) is confirmed live on this
-- tenant's 9-status workflow — "Partially Fulfilled," "Pending Billing,"
-- and "Pending Billing/Partially Fulfilled" have no matching label at all.
-- Rather than build on the one status that does match (too narrow) or wait
-- for a data-scientist call, Emilio decided to use the same "not Closed/
-- Cancelled" open-order proxy already used elsewhere in this pipeline.
-- Revisit if this ever looks too broad against real allocation data.
--
-- Job side: NetSuite's "Planned"/"Released" implemented as the inverse of
-- Part_v_Job_Status's Completed/Cancelled/Hold flags, same pattern as
-- labeling_open_work_orders_report and printing_open_work_orders_report —
-- not a specific status-text match, so it won't go stale if this tenant
-- adds status values.
--
-- Reads raw_Part_v_Job / raw_Part_v_Job_Status as SHARED tables owned and
-- extracted by the work_orders pipeline (same cross-pipeline pattern
-- work_orders_view.sql already uses for raw_Part_v_Part) — do not add
-- either as an extraction in sales_orders.yaml.
--
-- FIXED 2026-08-21 (caught in test deploy, not guessed): `Sales_v_Release_Job`
-- returned 0 rows on its first-ever extraction, so BigQuery autodetected all
-- 3 columns as STRING (same "empty table types everything STRING" gotcha
-- documented in catalog/plex_catalog_index.md for Job_Op.Workcenter_Key) —
-- while `Sales_v_Release.Release_Key`/`Part_v_Job.Job_Key` are already
-- INT64 from populated data. Both join conditions below need SAFE_CAST on
-- both sides or the view fails to create at all with "No matching
-- signature for operator =".
--
-- Extended 2026-08-23: SAFE_CAST both sides on every remaining join and the
-- WHERE filter too, not just the two that actually broke — the tables on
-- the other side of those (Sales_v_PO_Status, Common_v_Customer, Part_v_Part,
-- Part_v_Job_Status) are populated today, but any one of them empty on a
-- future run (same failure mode this view already hit once) would otherwise
-- break view creation the same way. All are no-ops today.
--
-- Not re-extracted beyond the new Sales_v_Release_Job link table — bq_view
-- entry in reports/sales_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per job allocated against a sales order release.

SELECT

  po.PO_No                                              AS document_so,
  sts.PO_Status                                          AS so_status,

  po.Customer_No,
  cust.Name                                             AS customer_name,

  p.Part_No                                             AS part_number,
  p.Name                                                AS part_name,

  rel.Quantity                                          AS qty_allocated,
  rel.Quantity_Unit                                     AS qty_unit,

  j.Job_No                                              AS job_no,
  js.Job_Status                                          AS job_status,
  j.Quantity                                            AS job_qty,
  j.Due_Date                                            AS job_due_date

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON po.PO_Key = pol.PO_Key

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON pol.PO_Line_Key = rel.PO_Line_Key

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release_Job` rj
  ON SAFE_CAST(rel.Release_Key AS INT64) = SAFE_CAST(rj.Release_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Job` j
  ON SAFE_CAST(rj.Job_Key AS INT64) = SAFE_CAST(j.Job_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(sts.PO_Status_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON SAFE_CAST(po.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(pol.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Job_Status` js
  ON SAFE_CAST(j.Job_Status_Key AS INT64) = SAFE_CAST(js.Job_Status_Key AS INT64)

-- SO side: "open" = not Closed (2074) / Cancelled (2076) — open-status
-- proxy decided 2026-08-21, see header note.
WHERE SAFE_CAST(po.PO_Status_Key AS INT64) NOT IN (2074, 2076)
  -- Job side: "open" = inverse of Completed/Cancelled/Hold, same pattern
  -- as labeling_open_work_orders_report/printing_open_work_orders_report.
  AND COALESCE(SAFE_CAST(js.Completed_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Cancelled_Status AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(js.Hold_Status AS INT64), 0) = 0
