# Sales Orders

> **Status:** ✅ Built and deployed to production 2026-08-22 (has been running against real Vox Nutrition data since 2026-07-13) · **Category:** Sales · **Runs:** `plex-etl`, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

One row per line item on a sales order — customer, sales rep(s), part ordered, quantity, price, and where the order sits in Vox's approval-to-shipment workflow (Pending Sales Approval → Deposit Review → Released → Pending Fulfillment → Pending Payment Review → Pending Shipment → Closed/Cancelled). This is the original, longest-running report in this pipeline — it went live before any of the other reports and is the base that several newer Sales reports (Open Sales Orders, Orders over $10k, Revenue per Sales Rep, and others) are built on top of.

## Where it fits

This is not a Google Sheet replacement — it's an original Plex-native report built directly for Vox. It's also the confirmed match for NetSuite's **"Vox | Open Sales Orders"** parity effort tracked in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) (item #76) and [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md) — that report (`sales_orders_open_report`) is a sibling view built from the exact same data, just filtered down to orders that aren't Closed or Cancelled yet. See [`reports-list/sales.md`](../../reports-list/sales.md) for the rest of the Sales report family this one anchors.

## How it's built (high level)

Starts from the sales order header and line items, then attaches everything a person would want to see next to an order: the customer's name, the primary and secondary sales rep, which part and how much was ordered, a price per unit (and a computed line total), the order's overall dollar total, and the product's type/group classification. It also figures out "Date Approved" by looking back through the order's status history for the first time it reached the "Pending Fulfillment" stage.

Because it returns one row per order line (not one row per order), an order with several parts on it will show up as several rows — that's expected, not a duplicate.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_orders_report`
- **SQL:** `reports/sql/sales_orders_view.sql`

## Flags and open questions

- **The per-unit price is a best-effort estimate, not a confirmed number.** Plex stores a customer's price in tiers based on order quantity; this report always picks the lowest-quantity tier as "the price." Nobody has confirmed this is the tier the business actually wants shown here — the SQL leaves a note to revisit if a different tier turns out to be the right one.
- **The line total (price × quantity) is computed, not a real Plex field.** There is no dollar-amount column on the order or line-item records in Plex at all, so this figure is this pipeline's own multiplication of the estimated price above by the ordered quantity, and excludes tax and freight. The order's overall total (`order_total`) is a real Plex value and is more trustworthy than the computed line total.
- **Not built:** a link back to the originating quote when an order started as one — Plex flags that an order came from a quote, but doesn't expose which quote's discount or terms it inherited.

## More detail

[`docs/CHEATSHEET.md`](../CHEATSHEET.md) has the full field-by-field mapping (which Plex view and column feeds each output column) and the complete status-code workflow.
