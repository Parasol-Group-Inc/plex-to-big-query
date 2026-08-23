# Report for Orders Past 14 Days Old

> **Status:** ✅ Deployed 2026-08-21, decided best-criteria — one open question flagged for review once real orders age · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

One row per open sales order line/release where the order was placed more than 14 days ago and still hasn't closed — customer, part, quantity, price, assigned sales rep, and how many days old the order is. It's a staleness list: orders that have been sitting open longer than expected and may need someone to follow up.

## Where it fits

This is a NetSuite parity report — it replaces the "Report for orders past 14 days old" saved search from NetSuite. Tracked in [`reports-list/sales.md`](../../reports-list/sales.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md).

## How it's built (high level)

Starts from the same order/line/release data already extracted for the Sales Orders report, applies the same "open" definition used by Open Sales Orders (excludes Closed and Cancelled orders), and adds one more filter on top: the order must have been placed 14 or more days before today. Each row also carries a "days old" count so you can see just how stale a given order is, not just that it crossed the threshold.

- **Pipeline:** `reports/sales_orders.yaml` -> `sales_orders_aging_report`
- **SQL:** `reports/sql/sales_orders_aging_view.sql`

## Flags and open questions

- **"14 days old" is measured from the order's original placement date, not confirmed against NetSuite.** The report counts age from when the order was first created (`PO_Date`). The alternative — counting from the date the order last changed status — wasn't verifiable without a screenshot of the real NetSuite search, so the simpler, already-available definition was kept. Flagged for review once real orders have had time to age past 14 days and the row counts can be sanity-checked.
- **Not built:** nothing else is known to be missing — the report otherwise mirrors the confirmed Open Sales Orders definition with just the age filter added.

## More detail

[`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md) has the full "PO_Date vs. last status change" decision and what would need to change to revisit it.
