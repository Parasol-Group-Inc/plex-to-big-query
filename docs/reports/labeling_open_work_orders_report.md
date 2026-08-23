# Labeling | Open WO: Results

> **Status:** ✅ Built and deployed · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per open job step running on a Labeling Line — job number, part, quantity, and due/start dates — for anyone who needs to see what's queued up for labeling right now. This is the Plex-native rebuild of a NetSuite saved search of the same name, so it answers the same question NetSuite used to ("which jobs are open and need labeling") without needing any NetSuite access at all.

## Where it fits

Rebuilds NetSuite's **"Labeling | Open WO: Results"** saved search, tracked in [`reports-list/production.md`](../../reports-list/production.md). It was initially written off as NetSuite-native and out of scope, then reconsidered once a screenshot of the actual saved-search criteria showed the underlying question was really about job status and workcenter — data Plex already tracks on its own.

## How it's built (high level)

Rides the same Job/Job Operation data already extracted for Work Orders and MFG Job Schedule, filtered down to just the Labeling Line workcenters and to jobs that are still open (not completed, cancelled, or on hold).

- **Pipeline:** `reports/work_orders.yaml` -> `labeling_open_work_orders_report`
- **SQL:** `reports/sql/labeling_open_work_orders_view.sql`

## Flags and open questions

- **One NetSuite filter has no Plex equivalent yet.** The original search also excluded any item whose name contains "lot traced." Nobody has found a matching flag or naming convention on the Plex side, so this report simply doesn't apply that exclusion rather than guess at it — some lot-traced items may show up here that NetSuite would have hidden.
- **"Open" is inferred, not NetSuite-confirmed.** NetSuite's "Released, In Process" statuses are mapped to the concept of a Plex job that isn't Completed, Cancelled, or on Hold, rather than to specific Plex status text — this is believed to be the right match conceptually, but nobody has verified it side-by-side against a real NetSuite result set.
- **Workcenter naming is confirmed live**, not guessed: this tenant's actual Labeling Line 1-6 workcenters were confirmed directly in the extracted Plex data, and a separate "Label Approval"/"Label Design" step (artwork approval, not physical labeling) was identified and deliberately excluded.

## More detail

See [`reports-list/production.md`](../../reports-list/production.md) for the fuller history of how this report was reconsidered and unblocked, and the SQL file's header comments for the exact mapping decisions.
