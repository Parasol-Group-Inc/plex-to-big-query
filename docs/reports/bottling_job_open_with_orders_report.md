# Bottling | Open Jobs with Sales Orders

> **Status:** 🛠 Brought into the repo 2026-10-26, not yet deployed from it (the hand-made copy in PlexProd already works) · **Category:** Production · **Runs:** rides the Work Orders pipeline

## What this tells you

Every open Bottling job with the sales order it is for: order number, customer, quantity pending, status and date entered.

## Where it came from

Jennilyn built it by hand in BigQuery on 2026-10-26 as a workaround. Plex's Job Distribution view, the obvious way to tie a job to an order, returns no rows on this tenant (prod and test). A question is open with the Plex champion (OPEN_ITEMS D20 area).

## How it picks the order

- **Direct:** the job was created from a sales order release. Most trustworthy.
- **Suggested:** no direct link. Shows the Pending Fulfillment orders for finished parts whose bill of materials uses this job's part; `fg_parts_using_this_part` names them. A guess, not a fact.
- Stock jobs show `Stock Job`; other job types show `N/A - <type>`; a Sales Order job with no match shows `No open order found`.

"Open" means the job is not Completed, Cancelled or On Hold, same as [`bottling_job_open_report.md`](bottling_job_open_report.md).

## How it's built (high level)

- **Pipeline:** `reports/work_orders.yaml` and `reports/test/work_orders.yaml` → `bottling_job_open_with_orders_report`
- **SQL:** `reports/sql/bottling_job_open_with_orders_view.sql` (Plex SQL Developer copy of the direct path: `reports/plex_sql/`)
- Reads `sales_orders_report` from the Sales Orders pipeline, so that one must exist first.

## Flags and open questions

- If Plex starts filling Job Distribution, replace the Suggested path with it.
- Suggested matches can list orders that have nothing to do with the job.
