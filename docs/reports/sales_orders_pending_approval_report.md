# Pending Approval Orders

> **Status:** ✅ Built and deployed, confirmed against live Plex data · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, prod 1 PM / 6 PM / 11 PM probe + 4 AM full (`PlexOps.etl_schedule`), test nightly

## What this tells you

Every sales order line item that's sitting brand-new in Plex, waiting for someone to approve it before work can start — customer, part, quantity, pricing, sales rep, all in one list. Same fields and layout as the main Sales Orders report, just narrowed down to only the orders still stuck at that first approval step.

## Where it fits

Plex-native replacement for the NetSuite report **"Pending Approval Orders"** — see [`reports-list/sales.md`](../../reports-list/sales.md) and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md).

## How it's built (high level)

Plex's sales order workflow has a literal status called "Pending Sales Approval" — it's the very first stop every new order lands on before it can move to Deposit Review or get Released. This report is just the full Sales Orders dataset filtered down to orders sitting in that exact status. No business-rule guessing was needed here — the status and its meaning were confirmed directly against Plex's own workflow configuration.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_orders_pending_approval_report`
- **SQL:** `reports/sql/sales_orders_pending_approval_view.sql`

Each row carries the order's **Order number** (`order_no`, added 2026-10-26, shown first, next to the PO number `document_so`), as in the Sales Orders report.

## Flags and open questions

- **Sales rep now resolves from the order, then the customer, then Order Salesperson (2026-10-29, audit B2).** The rep comes from the order's Inside Salesperson, then the customer's Assigned To, then Plex's Order Salesperson table, the same rule as the other sales views. The rep-table lookup no longer requires a Sort Order of exactly 1 or 2, which Plex often leaves blank or numbers differently; it takes the first and second rep on each order by Sort Order. A new `sales_rep_source` column says which of the three the rep came from (`order`, `customer`, `order_salesperson`). Most reps in prod come from Order Salesperson; a blank rep means Plex has none anywhere.
- **Prices come from the order line first (fixed 2026-10-19).** Order values use the price agreed on each order line (Plex's Sales Price), falling back to the customer price list only when a line has none. Before, they read the price list alone, and that list is **empty in Plex prod** (and never matched current parts in test), so every order value here was blank. On 19 Oct, 583 of 606 prod order lines had a line price. Row counts did not change; only the price columns filled in.
None known for this report itself — the "Pending Sales Approval" status and its meaning are confirmed live, not guessed.

One adjacent item worth knowing about: a second report, **Orders Pending Approval by Sales Rep**, was built as a thin alias directly on top of this one rather than as separate logic, because nobody had confirmed whether NetSuite's two report names actually describe different searches or the same data under two labels. If that ever turns out to be a genuinely different scope, that alias (not this report) is what would need to change.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) and [`docs/archive/NETSUITE_PARITY_OPEN_ITEMS.md`](../archive/NETSUITE_PARITY_OPEN_ITEMS.md) have the full confirmation log, including the related alias-report decision.
