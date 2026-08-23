# Orders over 10k bottles

> **Status:** ✅ Built and deployed 2026-08-21, best-criteria assumption not yet unit-confirmed · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

One row per sales order that adds up to 10,000+ units across all of its line items — order number, date, status, customer, and the total quantity that put it over the line. It's meant to flag Vox's largest-volume orders, the NetSuite parity report "Orders Over 10k Bottles."

## Where it fits

Fulfills a NetSuite saved search tracked in [`reports-list/sales.md`](../../reports-list/sales.md) and confirmed buildable in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md). It's one of several Sales parity reports added the same day alongside its sibling **Orders over $10k**. Also listed in [`docs/reports/REPORT_CATALOG.md`](REPORT_CATALOG.md).

## How it's built (high level)

Uses the same Sales Order header, line, release, status, and customer data already extracted for the Sales Orders report. For each order, it adds up the quantities across every release line to get one total-units number per order, then keeps only the orders where that total is 10,000 or more.

- **Pipeline:** `reports/sales_orders.yaml` -> `sales_orders_over_10k_bottles_report`
- **SQL:** `reports/sql/sales_orders_over_10k_bottles_view.sql`

## Flags and open questions

- **"10k bottles" is currently "10k units of anything on the order," not confirmed to be bottles specifically.** Plex's release records carry a unit-of-measure field alongside quantity, but no real order data existed on the test tenant to confirm which unit value(s) actually mean "bottles" versus cases, cartons, or other order units. Until that's confirmed, this report totals quantity across all units on an order regardless of what unit they're in — it may overcount if an order mixes bottle and non-bottle units together.
- **The unit(s) actually seen on each order are exposed on the report itself** (as a "quantity units seen" column) specifically so this can be checked and tightened once real orders exist — a data-scientist/Vox review is needed to confirm the right unit filter before fully trusting the 10k threshold.
- **No live-data contradiction found otherwise** — the join path (order -> line -> release -> customer/status lookups) is the same proven path used by the main Sales Orders report.

## More detail

[`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md) has this report's specific open question ("Which `Quantity_Unit` value(s) mean bottles?") alongside the same question for every other best-criteria Sales report decided the same day. [`reports-list/sales.md`](../../reports-list/sales.md) has the full NetSuite-search-by-search confirmation log this report came out of.
