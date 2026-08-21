-- sales_orders_pending_approval_by_rep_report — Vox | Orders Pending
-- Approval by Sales Rep (NetSuite parity, reports-list/sales.md)
--
-- DECIDED 2026-08-21 (best-criteria, NOT NetSuite-confirmed — adjust if
-- this comes out wrong): assumed to be the exact same underlying data as
-- "Pending Approval Orders" (sales_orders_pending_approval_report,
-- PO_Status_Key = 2585 "Pending Sales Approval") — NetSuite's saved-search
-- name never distinguished it from its sibling by anything other than
-- label text (see docs/NETSUITE_PARITY_OPEN_ITEMS.md). Built as a thin
-- alias view rather than a duplicated pipeline specifically so the two
-- can never silently drift apart — if this ever turns out to be a
-- genuinely different scope (e.g. "my own orders only," or a different
-- status), replace this SELECT with real logic instead of just editing it
-- to diverge from the source view.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.

SELECT * FROM `{gcp_project}.{dataset}.sales_orders_pending_approval_report`
