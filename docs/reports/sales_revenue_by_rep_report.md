# Revenue per Sales Rep

> **Status:** ✅ Deployed 2026-08-22 (prod), decided best-criteria · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

One row per sales order, showing which sales rep owns it and that order's computed revenue total — add up the rows for one rep to get their total book of business, or group by rep to compare reps against each other. This is the Plex-native answer to NetSuite's "Revenue per Sales Rep" saved search, built so Sales leadership can see revenue attributed to each rep without checking NetSuite. Orders with no rep on file are grouped under "Unassigned" rather than left out of the totals.

## Where it fits

Built as part of the 2026-08-14 sweep to find Plex equivalents for every NetSuite-sourced row in [`reports-list/sales.md`](../../reports-list/sales.md) (row: "Revenue per sales rep"). The confirmation history behind the revenue basis is in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md). It's the revenue-flavored sibling of **Customer List by Sales Rep** — both reports lean on the same per-order rep-assignment decision.

## How it's built (high level)

Reuses the same computed revenue used by the "Orders over $10k" report — each order line's customer price times the quantity ordered, summed up per order, with no tax or freight added in — and attaches that total to whichever rep is marked as the order's primary salesperson. A secondary rep on the same order isn't also credited with that revenue, so the same dollars aren't counted twice. Orders that don't have a rep on file at all still show up, just grouped under "Unassigned" instead of being dropped from the numbers.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_revenue_by_rep_report`
- **SQL:** `reports/sql/sales_revenue_by_rep_view.sql`

## Flags and open questions

- **The revenue figure is a best-criteria computed total, not NetSuite-confirmed.** It's the same base-tier price × quantity calculation used by the Orders over $10k report, chosen because Plex has no real dollar-total field to read directly. It excludes tax and freight. The SQL file itself flags this for data-scientist review before anyone treats these totals as ground truth.
- **Rep assignment is per-order, not a standing customer relationship.** Plex has no field that says "this customer belongs to this rep" — a rep only shows up because they're listed on that specific order. Same caveat that applies to Customer List by Sales Rep.
- **"Unassigned" is a real bucket, size unknown.** Any order without a rep row rolls up into an "Unassigned" total rather than disappearing — nobody has checked yet how much revenue lands there once real order volume is flowing.
- **Report is untested against real production order volume.** It's confirmed to deploy and query correctly, but has only been checked against the small number of live orders on the test tenant so far.

## More detail

[`reports-list/sales.md`](../../reports-list/sales.md) and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) have the full live-confirmation history behind the revenue basis and the per-order rep-assignment decision.
