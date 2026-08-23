# RUSH Open Sales Orders

> **Status:** ✅ Deployed to test 2026-08-21, promoted to production 2026-08-22 · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

One row per open sales order line — every sales order that is still open (not Closed, Cancelled, or Pending Sales Approval) **and** whose memo/note field contains the word "RUSH." This is the Plex-native replacement for NetSuite's "ATL | RUSH Open SOs" saved search (also seen internally as "Vox | RUSH Open Sos" / "One for Rush orders"), used to flag orders that need expedited handling.

## Where it fits

Fulfills a NetSuite parity item tracked in [`reports-list/sales.md`](../../reports-list/sales.md) (and cross-referenced from [`reports-list/production.md`](../../reports-list/production.md)). The resolution history is also logged in [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md) and [`CHANGELOG.md`](../../CHANGELOG.md) (2026-08-21 entries).

## How it's built (high level)

For a long time this report was blocked: the obvious lead was that NetSuite might have a dedicated "Rush" priority flag on the order, but the Plex equivalent of that field came back empty on every order, so it looked like a dead end. Screenshots of the real NetSuite search settled it — there is no priority flag involved at all. "RUSH" is a plain-text convention: whoever enters the order types "RUSH" at the start of the memo/note field (a real example: "RUSH | New label review..."). So this report simply looks for orders whose note field contains the word RUSH, the same way a person would scan the memo column by eye.

From there it reuses the same order → line → release → part join already used for the general Open Sales Orders report, with one extra status excluded (Pending Sales Approval) to match this search's specific definition of "open," plus the RUSH text filter.

- **Pipeline:** `reports/sales_orders.yaml` -> `sales_orders_rush_open_report`
- **SQL:** `reports/sql/sales_orders_rush_open_view.sql`

## Flags and open questions

- **Unconfirmed against real RUSH orders.** Plex and NetSuite are entered separately, so it isn't proven that whoever enters orders in Plex uses the same "RUSH | ..." memo convention Vox uses in NetSuite. On the test tenant's 9 real live sales orders, none currently contain "RUSH" in the note field — inconclusive on a sample this small, not disproven. Flag for data-scientist review before trusting row counts once more real orders exist.
- **"Billed" status has no Plex equivalent.** NetSuite's version of this search also excludes orders marked "Billed." Plex's order-status workflow has no separate billed/invoiced state, so this report assumes those orders are already covered by "Closed" rather than guessing at a different status. If an order is ever seen sitting in "Closed" while still unbilled, that assumption needs revisiting.
- **Line-level noise filters not applied.** NetSuite's search also excludes certain non-physical line types (discounts, kits, service charges, etc.) and non-taxable items. This report doesn't filter those out — same as every other Sales Orders report in this pipeline — because it's unconfirmed whether Plex's line data even has that kind of distinction to filter on.

## More detail

See [`reports-list/sales.md`](../../reports-list/sales.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md) for the full resolution history, including the earlier dead-end lead and the screenshots that unblocked this report.
