# Orders Pending Approval by Sales Rep

> **Status:** ✅ Built 2026-08-21, decided best-criteria — same underlying data as "Pending Approval Orders," not independently confirmed as a distinct report · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

The same list as "Pending Approval Orders" — every sales order line still sitting in Plex's "Pending Sales Approval" status, with the assigned sales rep(s), customer, part, quantity, and price on each row — just delivered under NetSuite's separate saved-search name. If you're looking for "which orders are waiting on sales approval," this and "Pending Approval Orders" show you the exact same rows.

## Where it fits

NetSuite parity for the **"Orders Pending Approval by Sales Rep"** saved search tracked in [`reports-list/sales.md`](../../reports-list/sales.md). See [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md) and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) for the full reasoning behind how it was built.

## How it's built (high level)

NetSuite's saved-search list had two entries — "Pending Approval Orders" and "Orders Pending Approval by Sales Rep" — with nothing beyond the label text to say whether they were really two different reports or the same data described two ways. Rather than guess at a second, possibly-wrong filter and risk quietly shipping a duplicate report with different numbers, this was built as a direct copy of "Pending Approval Orders": same status filter, same joins, same columns. If it's ever confirmed that the real NetSuite report was scoped differently (for example, only a rep's own orders), this can be rebuilt with real logic instead.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_orders_pending_approval_by_rep_report`
- **SQL:** `reports/sql/sales_orders_pending_approval_by_rep_view.sql` (a one-line pass-through of `sales_orders_pending_approval_report`)

## Flags and open questions

- **Not independently confirmed as its own report.** This was a deliberate decision, not an oversight: nobody has seen the real NetSuite search definition, so there's no way yet to know if "by Sales Rep" was ever meant to be a different slice of the data (e.g., filtered to one rep's own orders) rather than just a relabeled copy of the status-based list. Revisit if that turns out to be wrong.
- **Inherits every open question from "Pending Approval Orders."** Because this is a straight copy, anything unconfirmed there (pricing basis, secondary sales rep coverage) carries over here too — see [`sales_orders_pending_approval_report.md`](sales_orders_pending_approval_report.md).
- **Built to never silently drift from its source.** Because it's a live pass-through rather than a duplicated pipeline, any future fix or change to "Pending Approval Orders" automatically applies here too — the two can't quietly show different numbers by accident.

## More detail

[`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md) has the specific decision record for this report, and [`reports-list/sales.md`](../../reports-list/sales.md) has the full department-wide inventory it fits into.
