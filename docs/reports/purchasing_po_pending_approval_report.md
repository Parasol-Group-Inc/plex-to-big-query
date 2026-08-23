# Purchase Orders to Approve: Results

> **Status:** ✅ Built and confirmed — filtered on Plex's own literal status label, no business-rule guessing involved · **Category:** Supply Chain · **Runs:** rides the Purchasing Open Orders pipeline, 7:40 PM / 7:50 PM Mountain (prod/test)

## What this tells you

One row per purchase order line (per delivery release, if a line has more than one), listing every supplier PO that is currently sitting in Plex's **"Pending Approval-NS"** status — i.e. created but not yet approved to move forward to "On Order." Each row shows the PO number, date created, order type, supplier, part, quantity ordered, and due date, plus the raw status so it's obvious why the row is on this list. This is the Plex-native replacement for the NetSuite saved search **"Purchase Orders to Approve"** (also seen as "Purchase Orders to Approve for Shelby/Alisa/COO/Director" — several personalized copies of the same underlying search existed in NetSuite).

## Where it fits

Fulfills the NetSuite report **Purchase Orders to Approve: Results**, tracked in [`reports-list/supply-chain.md`](../../reports-list/supply-chain.md) and [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md). No Google Sheet equivalent — this one only ever existed as a NetSuite saved search, so there's nothing in `spreadsheets/` for it. Confirmed as a clean, no-guesswork build in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md)'s 2026-08-14 sweep.

## How it's built (high level)

This is a second, differently-filtered view on top of the same data already pulled for the **Purchasing Open Orders** report: the same PO header, line item, release schedule, supplier, and part data, just narrowed down to the one status that means "awaiting approval." Plex's purchase order workflow has a distinct status called "Pending Approval-NS" that sits between "New" and "On Order" — that's a literal, already-configured value in Plex's own status list, not something reconstructed or guessed at, so this report is as close to a sure thing as this pipeline gets.

- **Pipeline:** `reports/purchasing_open_orders.yaml` -> `purchasing_po_pending_approval_report`
- **SQL:** `reports/sql/purchasing_po_pending_approval_view.sql`

## Flags and open questions

None known. The filter is Plex's own named status ("Pending Approval-NS," status key 5559), confirmed present in the live status workflow — this was one of the few NetSuite-parity reports in the 2026-08-14 sweep that needed no business-rule assumption at all. The one thing nobody has separately checked is how many real POs currently sit in that status day-to-day (the confirmation pass verified the status *exists* in Plex's schema, not a live row count against it) — worth a glance the first time this report is used for real, but not a reason to doubt the logic.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) has the full confirmation notes for this and the rest of the 2026-08-14 NetSuite-parity batch. `reports/sql/purchasing_open_orders_view.sql` — the sibling view on the same pipeline — carries the shared join/field notes in its header comments.
