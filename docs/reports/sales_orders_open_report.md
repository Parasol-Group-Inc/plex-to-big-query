# Vox | Open Sales Orders

> **Status:** ✅ Built and deployed 2026-08-10, confirmed against real data · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

One row per sales order line/release — the same order, customer, part, sales rep, and pricing detail as the full Sales Orders report, but narrowed down to only the orders that are still open. This is the Plex-native replacement for NetSuite's "Vox | Open Sales Orders" report.

## Where it fits

This is NetSuite parity report **#76** from [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md#76--vox--open-sales-orders--sales_orders_open_report--done), tracked as an exact-name match in [`mapping/netsuite-report-mapping.md`](../../mapping/netsuite-report-mapping.md) and listed in [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md). It doesn't have its own Google Sheet — it's a straight NetSuite-to-Plex rebuild, not a replacement for manually tracked spreadsheet.

## How it's built (high level)

Starts from the exact same sales order data as the main [Sales Orders report](sales_orders_report.md) — order header, line items, customer, sales rep, part, and pricing — and adds one thing: a filter that drops any order whose status is Closed or Cancelled, so only orders still in motion show up.

"Open" here was confirmed directly with the report requester as a status-based definition (exclude Closed and Cancelled only) — it is not based on ship dates, quantities remaining, or anything else. That definition was checked against Plex's own status-code list before shipping, so it isn't a guess.

- **Pipeline:** `reports/sales_orders.yaml` -> `sales_orders_open_report`
- **SQL:** `reports/sql/sales_orders_open_view.sql`

## Flags and open questions

- None known. The "open" filter logic was confirmed with the report requester and cross-checked against Plex's status-code reference before deployment, and the report was verified against a real Cloud Run execution (3 open orders out of 4 total on the test tenant) rather than just a schema-level check.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md#76--vox--open-sales-orders--sales_orders_open_report--done) has the full research and confirmation history for this report, including the resolved business question about what "open" means. [`docs/reports/sales_orders_report.md`](sales_orders_report.md) covers the shared field-by-field detail (customer, rep, pricing, product classification) this report inherits.
