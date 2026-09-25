# Orders Pending Approval by Accounting

> **Status:** ⚠ Repointed 2026-09-09 after the status it targeted was deleted in Plex — returns 2 rows again, but the new status choice needs confirming · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

One row per order line/release that's sitting at the "Pending Payment Review" status — order, customer, sales rep(s), part, quantity, and price. This is the Plex-native answer to NetSuite's "Orders Pending Approval by Accounting" search: the list Accounting would work from to see what's waiting on them before an order can keep moving.

## Where it fits

Built as NetSuite parity, tracked in [`reports-list/sales.md`](../../reports-list/sales.md). Also logged in the decisions table in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) and [`docs/archive/NETSUITE_PARITY_OPEN_ITEMS.md`](../archive/NETSUITE_PARITY_OPEN_ITEMS.md).

## How it's built (high level)

Uses the same order/customer/rep/part/price data already extracted for the Sales Orders report, filtered down to one specific status in Plex's order workflow. Of all the confirmed statuses an order can be in, only one reads as accounting-related — "Pending Payment Review" — so that's the stage this report shows.

- **Pipeline:** `reports/sales_orders.yaml` -> `sales_orders_pending_accounting_approval_report`
- **SQL:** `reports/sql/sales_orders_pending_accounting_approval_view.sql`

## Flags and open questions

- **⚠ Dead a second time, fixed 2026-09-24.** Plex now has **two** Deposit Review statuses — "Deposit Review (Initiate Payment Request)" (2587) and "Deposit Review (Bypass Payment Request)" (2656) — and the exact-name match on `DEPOSIT REVIEW` found neither. The filter is now `LIKE 'DEPOSIT REVIEW%'`, which catches both and any future variant. The rep column (`sales_rep_1`) was also repointed to the order's Inside Salesperson, then the customer's Assigned To, as in [`sales_mtd_by_status_change_report`](sales_mtd_by_status_change_report.md). Found by the scorecard sandbox.
- **⚠ This report was silently dead, and nothing would have revealed it.** It filtered the order status **Pending Payment Review**, and on 2026-09-09 Vox consolidated their sales-order statuses from 10 down to 7 — that status, along with Pending Shipment and Quote Lost, **no longer exists**. The report returned zero rows, which reads exactly like "no orders are pending accounting approval" rather than "this filter can never match anything ever again." A sweep of every report SQL file for the three deleted statuses found this as the only one affected.
- **⚠ Repointed to Deposit Review — and this is the second guess, so please confirm it.** In the new 7-status list, Deposit Review is the only accounting-flavoured stage (a deposit is a money gate, sitting between Pending Sales Approval and Pending Fulfillment). It now returns **2 real rows**. But the original "Pending Payment Review" choice was *also* a reasonable-looking inference that was flagged for review and never confirmed — and it was wrong-by-deletion within three weeks. The **`status`** column is in the output so you can see which status produced each row rather than taking this doc's word for it.
- **The filter now matches on the status name, not its numeric key.** A key that vanished is precisely what broke this report; a rename is easier to spot than a silent empty result.

## More detail

See the SQL file's header comment for the exact status key and the reasoning behind it, and [`reports-list/sales.md`](../../reports-list/sales.md) for how this fits alongside the other Sales-tab NetSuite parity reports.
