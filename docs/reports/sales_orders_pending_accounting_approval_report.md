# Orders Pending Approval by Accounting

> **Status:** ✅ Built and deployed 2026-08-21 · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

One row per order line/release that's sitting at the "Pending Payment Review" status — order, customer, sales rep(s), part, quantity, and price. This is the Plex-native answer to NetSuite's "Orders Pending Approval by Accounting" search: the list Accounting would work from to see what's waiting on them before an order can keep moving.

## Where it fits

Built as NetSuite parity, tracked in [`reports-list/sales.md`](../../reports-list/sales.md). Also logged in the decisions table in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md).

## How it's built (high level)

Uses the same order/customer/rep/part/price data already extracted for the Sales Orders report, filtered down to one specific status in Plex's order workflow. Of all the confirmed statuses an order can be in, only one reads as accounting-related — "Pending Payment Review" — so that's the stage this report shows.

- **Pipeline:** `reports/sales_orders.yaml` -> `sales_orders_pending_accounting_approval_report`
- **SQL:** `reports/sql/sales_orders_pending_accounting_approval_view.sql`

## Flags and open questions

- **The status choice is a best-criteria guess, not NetSuite-confirmed.** "Pending Payment Review" is the only accounting-flavored stage in Plex's confirmed order-status workflow, and it sits in a plausible spot (after Released/Pending Fulfillment, before Pending Shipment) — but nobody has checked this against a real NetSuite screenshot of the "by Accounting" search. Flagged for data-scientist review before trusting this report's row counts.
- **This was a 2026-08-21 decision to keep, not a new finding** — the same status choice was reconsidered and confirmed as "no better candidate exists" rather than replaced.

## More detail

See the SQL file's header comment for the exact status key and the reasoning behind it, and [`reports-list/sales.md`](../../reports-list/sales.md) for how this fits alongside the other Sales-tab NetSuite parity reports.
