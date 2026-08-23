# Vox | Open RMA's

> **Status:** ✅ Built, deployed, and verified 2026-08-23 · **Category:** Sales · **Runs:** own Cloud Run job, 10:20 PM / 10:30 PM Mountain (prod/test)

## What this tells you

One row per customer return (RMA) that's still open — not yet Closed or Cancelled. For each one: the return number, when it was created, its current status, the customer, the related sales order, and a description. It's meant to answer "which customer returns are still in progress and need attention?"

## Where it fits

This is a NetSuite parity report — it replaces the "Open RMA's" saved search from NetSuite. Tracked in [`reports-list/sales.md`](../../reports-list/sales.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md).

## How it's built (high level)

Pulls from a new pair of Plex views built specifically for this report (returns and their statuses), then adds the customer name by matching against the same customer list already extracted for Sales Orders. A return counts as "open" if its status isn't Closed or Cancelled — the same not-yet-terminal pattern already used for Open Quotes and the open-orders reports elsewhere in Sales.

- **Pipeline:** `reports/sales_returns.yaml` -> `sales_returns_open_report`
- **SQL:** `reports/sql/sales_returns_open_view.sql`

## Flags and open questions

- **The first real run failed to build the view.** `raw_Sales_v_Return` had 0 rows, so BigQuery auto-typed it all-`STRING`, while `raw_Sales_v_Return_Status` and `raw_Common_v_Customer` both have real data and are properly typed (`INT64`); joining without a cast fails outright. Fixed same day with `SAFE_CAST` on both sides of every join and the status-exclusion filter. Re-verified by directly querying the view (a Cloud Run job can exit successfully even when the view itself failed to build).
- **Not yet verified against a real return.** The test tenant had zero rows in the underlying return data at the time this was built, so the "open" filter is confirmed correct against the live status list (matching real, distinct Closed/Cancelled statuses) but has never been checked against an actual in-progress RMA. The view now builds and queries cleanly, but row counts still shouldn't be trusted until real return activity exists.
- **"Open RMA's" as the intended NetSuite definition was never confirmed by a screenshot** — the status-exclusion approach (not Closed/Cancelled) is the same convention used successfully elsewhere in this pipeline, and was kept as the working definition rather than waiting on a data-scientist review, but nobody has verified it's exactly what the original NetSuite report showed.
- **A more specific "in progress" flag was considered and rejected.** The status table has boolean columns for Received/Assigned/Approved/Pending, but these were confirmed live to be all-zero across every status — same gap seen on the Supplier Return side of this pipeline — so they couldn't be used, and the simpler exclusion-list approach was used instead.

## More detail

[`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md) has the full decision history, [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) has the original confirmation log, and [`reports-list/sales.md`](../../reports-list/sales.md) has the original NetSuite search this replaces.
