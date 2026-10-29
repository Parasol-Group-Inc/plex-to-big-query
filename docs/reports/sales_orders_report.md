# Sales Orders

> **Status:** ✅ Built and deployed to production 2026-08-22 (has been running against real Vox Nutrition data since 2026-07-13) · **Category:** Sales · **Runs:** `plex-etl-sales-orders`, prod 1 PM / 6 PM / 11 PM probe + 4 AM full (`PlexOps.etl_schedule`), test nightly

## What this tells you

One row per line item on a sales order — customer, sales rep(s), part ordered, quantity, price, and where the order sits in Vox's approval-to-shipment workflow (Pending Sales Approval → Deposit Review → Released → Pending Fulfillment → Pending Payment Review → Pending Shipment → Closed/Cancelled). This is the original, longest-running report in this pipeline — it went live before any of the other reports and is the base that several newer Sales reports (Open Sales Orders, Orders over $10k, Revenue per Sales Rep, and others) are built on top of.

## Where it fits

This is not a Google Sheet replacement — it's an original Plex-native report built directly for Vox. It's also the confirmed match for NetSuite's **"Vox | Open Sales Orders"** parity effort tracked in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) (item #76) and [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md) — that report (`sales_orders_open_report`) is a sibling view built from the exact same data, just filtered down to orders that aren't Closed or Cancelled yet. See [`reports-list/sales.md`](../../reports-list/sales.md) for the rest of the Sales report family this one anchors.

## How it's built (high level)

Starts from the sales order header and line items, then attaches everything a person would want to see next to an order: the customer's name, the primary and secondary sales rep, which part and how much was ordered, a price per unit (and a computed line total), the order's overall dollar total, and the product's type/group classification. It also figures out "Date Approved" by looking back through the order's status history for the first time it reached the "Pending Fulfillment" stage.

Each row carries both the order's **Order number** (`order_no`, added 2026-10-26, shown first) and its **PO number** (`document_so`), the two separate numbers Plex keeps on a sales order.

Because it returns one row per order line (not one row per order), an order with several parts on it will show up as several rows — that's expected, not a duplicate.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_orders_report`
- **SQL:** `reports/sql/sales_orders_view.sql`

## Flags and open questions

- **Sales rep now resolves from the order, then the customer, then Order Salesperson (2026-10-29, audit B2).** The rep comes from the order's Inside Salesperson, then the customer's Assigned To, then Plex's Order Salesperson table, the same rule as the other sales views. The rep-table lookup no longer requires a Sort Order of exactly 1 or 2, which Plex often leaves blank or numbers differently; it takes the first and second rep on each order by Sort Order. A new `sales_rep_source` column says which of the three the rep came from (`order`, `customer`, `order_salesperson`). Most reps in prod come from Order Salesperson; a blank rep means Plex has none anywhere.
- **`order_total` is now the sum of the order's line totals (2026-10-29, audit B4).** It used to read Plex's `Master_Price`, which is 0 on every prod order, so the column was always 0. It now adds up price × quantity across every line of the order, using the same price as the line total. On 29 Oct, 874 of 924 prod rows had a total.
- **New `line_no` column (2026-10-29, audit B11).** Rows of one order looked like duplicates because nothing told them apart. `line_no` numbers each order's lines 1, 2, 3 in the order they were entered. Plex's own Line_No holds the same value on every line, so it is not used.
- **Prices come from the order line first (fixed 2026-10-19).** Order values use the price agreed on each order line (Plex's Sales Price), falling back to the customer price list only when a line has none. Before, they read the price list alone, and that list is **empty in Plex prod** (and never matched current parts in test), so every order value here was blank. On 19 Oct, 583 of 606 prod order lines had a line price. Row counts did not change; only the price columns filled in.
- **⚠ Fixed 2026-09-24 — `product_group` was always blank.** It joined `Part_v_Part.Part_Group_Key` to `Part_v_Part_Product_Group`, which is empty in test and prod. It now reads Plex's **Part Group** (`Part_v_Part_Group`: Capsule, Softgel, Label, Packaging, ...), which is what that key actually points at; the column keeps its `product_group` name. `raw_Part_v_Part_Group` is newly extracted by this pipeline, and the fix was **deployed 2026-09-25** — the names show in PlexTest now, and in PlexProd from the first scheduled Sales Orders run after the deploy.
- **The per-unit price is a best-effort estimate, not a confirmed number.** Plex stores a customer's price in tiers based on order quantity; this report always picks the lowest-quantity tier as "the price." Nobody has confirmed this is the tier the business actually wants shown here — the SQL leaves a note to revisit if a different tier turns out to be the right one.
- **The line total (price × quantity) is computed, not a real Plex field.** There is no dollar-amount column on the order or line-item records in Plex at all, so this figure is this pipeline's own multiplication of the estimated price above by the ordered quantity, and excludes tax and freight. The order's total (`order_total`) is the sum of these line totals.
- **Not built:** a link back to the originating quote when an order started as one — Plex flags that an order came from a quote, but doesn't expose which quote's discount or terms it inherited.

## More detail

[`docs/CHEATSHEET.md`](../CHEATSHEET.md) has the full field-by-field mapping (which Plex view and column feeds each output column) and the complete status-code workflow.
