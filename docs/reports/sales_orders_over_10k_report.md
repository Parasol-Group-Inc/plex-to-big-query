# Orders over $10k

> **Status:** ✅ Deployed 2026-08-22 (prod), decided best-criteria · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

One row per sales order whose total value comes out to $10,000 or more — order number, date, status, customer, and the computed order total. This is the Plex-native answer to NetSuite's "Orders over $10k" saved search, built so Sales/Accounting can spot large orders without checking NetSuite.

## Where it fits

Built as part of the 2026-08-14 sweep to find Plex equivalents for every NetSuite-sourced row in [`reports-list/sales.md`](../../reports-list/sales.md) (row: "Orders over $10k"). The confirmation history for the $10k basis decision is in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md).

## How it's built (high level)

Plex doesn't store an order-total dollar amount anywhere on the order or its line items — that field simply doesn't exist in the source data. So this report computes one: for each order line, it takes the customer's base-tier price for that part and multiplies it by the quantity on the order, then adds those up per order. Orders whose computed total is $10,000 or more make the list. This computed total does not include tax or freight, and it does not use the `Master_Price` field that sometimes appears on the order header — that field is a fallback candidate, not what's used today.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_orders_over_10k_report`
- **SQL:** `reports/sql/sales_orders_over_10k_view.sql`

## Flags and open questions

- **The $10k basis is a best-criteria decision, not NetSuite-confirmed.** Because no real "order total" field exists in Plex, the computed base-price × quantity total was chosen as "the only basis with real data behind it" — nobody has verified this matches how NetSuite (or Vox's own definition) actually measures "$10k" per order. A data-scientist review should confirm whether this computed total is the right yardstick, or whether `Master_Price` (where it's actually populated) should be used instead.
- **Tax and freight are excluded** from the computed total by design — an order could be under $10k here but over $10k once tax/freight is added, or vice versa if those aren't normally material.
- **Report is untested against real production order volume.** It was confirmed to deploy and query correctly, but has only been checked against the small number of live orders on the test tenant so far — the $10k cutoff hasn't been validated against a real, larger book of business yet.

## More detail

[`reports-list/sales.md`](../../reports-list/sales.md) and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) have the full live-confirmation history behind the $10k basis decision, including why the dollar-column search came up empty and what was checked before settling on the computed total.
