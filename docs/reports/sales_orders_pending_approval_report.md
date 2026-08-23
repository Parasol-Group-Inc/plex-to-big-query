# Pending Approval Orders

> **Status:** ✅ Built and deployed, confirmed against live Plex data · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

Every sales order line item that's sitting brand-new in Plex, waiting for someone to approve it before work can start — customer, part, quantity, pricing, sales rep, all in one list. Same fields and layout as the main Sales Orders report, just narrowed down to only the orders still stuck at that first approval step.

## Where it fits

Plex-native replacement for the NetSuite report **"Pending Approval Orders"** — see [`reports-list/sales.md`](../../reports-list/sales.md) and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md).

## How it's built (high level)

Plex's sales order workflow has a literal status called "Pending Sales Approval" — it's the very first stop every new order lands on before it can move to Deposit Review or get Released. This report is just the full Sales Orders dataset filtered down to orders sitting in that exact status. No business-rule guessing was needed here — the status and its meaning were confirmed directly against Plex's own workflow configuration.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_orders_pending_approval_report`
- **SQL:** `reports/sql/sales_orders_pending_approval_view.sql`

## Flags and open questions

None known for this report itself — the "Pending Sales Approval" status and its meaning are confirmed live, not guessed.

One adjacent item worth knowing about: a second report, **Orders Pending Approval by Sales Rep**, was built as a thin alias directly on top of this one rather than as separate logic, because nobody had confirmed whether NetSuite's two report names actually describe different searches or the same data under two labels. If that ever turns out to be a genuinely different scope, that alias (not this report) is what would need to change.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md) have the full confirmation log, including the related alias-report decision.
