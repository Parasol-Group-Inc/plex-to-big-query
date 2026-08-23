# Printing Open Work Orders

> **Status:** ✅ Built and deployed · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per open job operation running on the Printing workcenter — job number, part, part name, job status, planned quantity, and the operation's due/start dates. It's meant to answer "what's still open on Printing right now," the same question NetSuite's "Printing Open Work Orders" saved search answered before this data lived in Plex.

## Where it fits

This is the Plex-native replacement for NetSuite's **Printing Open Work Orders** saved search, tracked in [`reports-list/sales.md`](../../reports-list/sales.md) (it's listed on the Sales tab because that's where NetSuite filed it, but it's a Production report in substance — same as its sibling below). It's an exact structural twin of **Labeling | Open WO: Results**, just pointed at a different workcenter — see [`reports-list/production.md`](../../reports-list/production.md) and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md) for both reports' shared history.

## How it's built (high level)

Takes the same Job/Job Operation/Workcenter data already extracted for Work Orders and MFG Job Schedule, filters it down to job operations on a Printing workcenter, and keeps only the ones that aren't Completed, Cancelled, or on Hold.

- **Pipeline:** `reports/work_orders.yaml` -> `printing_open_work_orders_report`
- **SQL:** `reports/sql/printing_open_work_orders_view.sql`

## Flags and open questions

- **"Open" is an inferred definition, not a confirmed match to NetSuite's actual criteria.** Nobody had a screenshot of the real saved search's filter logic, so "open" here means "not flagged Completed, Cancelled, or Hold" on the job's status — a reasonable proxy, but it's not verified to line up with whatever NetSuite's search literally checked.
- **The workcenter filter is a text-pattern match (`Printing%`), not a clean category lookup.** Confirmed live and working, but a cleaner `Workcenter_Group = 'Printing'` field has since been identified in the Plex workcenter catalog as the better long-term way to do this match — not urgent to change since the current version works, but worth switching to eventually.
- **No real production data has moved through this report yet** — everything above is confirmed against the Plex schema and a live workcenter, not against a finished/aged batch of real Printing jobs.

## More detail

No dedicated spreadsheet or build-plan doc exists just for this report — its full origin story (the NetSuite saved search review, the Labeling twin it's based on, and the status-mapping assumption) is documented inline in [`reports/sql/printing_open_work_orders_view.sql`](../../reports/sql/printing_open_work_orders_view.sql) and in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../../docs/NETSUITE_REPORT_BUILD_PLAN.md).
