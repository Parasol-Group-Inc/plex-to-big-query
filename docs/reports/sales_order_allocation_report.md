# Vox | Allocation Report

> **Status:** ✅ Deployed to test 2026-08-21, decided open-status proxy — currently returns 0 rows on real data, needs a data-scientist/Vox answer · **Category:** Sales · **Runs:** rides the Sales Orders pipeline, 7:00 PM / 7:10 PM Mountain (prod/test)

## What this tells you

One row per production job that was generated from a sales order and is still open on both sides — the order hasn't finished shipping/billing, and the job itself hasn't been completed, cancelled, or put on hold. For each one: the sales order, customer, part, how much was allocated to that job, and the job's own status, quantity, and due date. It's meant to answer "which jobs on the floor right now are actually tied to a specific customer order, and where do things stand on both ends?"

## Where it fits

This is a NetSuite parity report — it replaces the "Vox | Allocation Report" saved search from NetSuite. Tracked in [`reports-list/sales.md`](../../reports-list/sales.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md).

## How it's built (high level)

Starts from the same sales order and line data already extracted for the Sales Orders report, then follows the chain from an order line down to the specific release (the scheduled shipment of a quantity) and from there to whichever production job was created to fulfill it. It keeps only jobs where the order side is still open (not Closed/Cancelled) and the job side is still open (not Completed/Cancelled/On Hold), then adds the job's own status, quantity, and due date alongside the order and customer info. The job data itself is shared with the Work Orders pipeline rather than pulled twice.

- **Pipeline:** `reports/sales_orders.yaml` -> `sales_order_allocation_report`
- **SQL:** `reports/sql/sales_order_allocation_view.sql`

## Flags and open questions

- **Currently returns 0 rows on real data — needs a data-scientist/Vox answer.** The link table between a sales order release and the job it's allocated to (`Sales_v_Release_Job`) is completely empty on this tenant, even though both sides it's supposed to connect have real rows (8 releases, 16 jobs). Until someone confirms whether Vox actually populates job-to-release links in Plex, this report has no way to show anything, regardless of how many open orders or jobs exist.
- **The "open order" definition is a stand-in, not a confirmed match.** NetSuite's real filter checks for one of four specific order statuses (Partially Fulfilled, Pending Billing, Pending Billing/Partially Fulfilled, Pending Fulfillment). Only "Pending Fulfillment" has a matching status in Plex on this tenant — the other three don't exist here at all. Rather than build on that one narrow match or wait on a data-scientist review, the report uses the same "anything not Closed or Cancelled" proxy already used for Open Quotes and Open RMAs. Revisit if this ever looks too broad once real allocation data exists.
- **The "open job" definition (Planned/Released) is also a proxy**, built the same way the Labeling/Printing Open Work Orders reports handle it: a job counts as open if it isn't flagged Completed, Cancelled, or On Hold, rather than matching specific status text. This is intentional — it won't go stale if new status values get added later.
- **A real data-type bug was caught and fixed before this went live.** Because the release-to-job link table had zero rows the first time it was pulled from Plex, BigQuery guessed all of its columns were text instead of numbers, which broke the join against the job and release tables. This has been fixed (with an explicit numeric conversion on both sides of the join), so it won't block the report once real linked data shows up — but it's a reminder that a newly-added, still-empty table can misbehave like this the first time.

## More detail

[`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../../docs/NETSUITE_PARITY_OPEN_ITEMS.md) has the full decision history, and [`reports-list/sales.md`](../../reports-list/sales.md) has the original NetSuite search this replaces.
