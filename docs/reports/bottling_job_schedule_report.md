# Bottling Job Schedule

> **Status:** ✅ Built and deployed 2026-08-22, awaiting real production data to confirm two exploratory columns · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per bottling job step — which part is running on which Bottling line, how many bottles/pills are planned, who worked it, and (once real production data exists) how long each step actually took. This is the Plex-native replacement for the manually maintained "Bottling Job Schedule" Google Sheet.

## Where it fits

Fulfills the **Bottling Job Schedule** Google Sheet tracked in [`spreadsheets/bottling_job_schedule.md`](../../spreadsheets/bottling_job_schedule.md) — the bottling-specific sibling of MFG Job Schedule. Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Filters the same Job/Job Operation data already extracted for Work Orders and MFG Job Schedule down to just the Bottling workcenters (Bottling Line 1–6, Bulk Room, Powder Line, Liquid Line), then adds the columns specific to this sheet: which lot was used, who ran the job, and a first attempt at reconstructing "how long did this take" from the operation's start/finish times.

- **Pipeline:** `reports/work_orders.yaml` → `bottling_job_schedule_report`
- **SQL:** `reports/sql/bottling_job_schedule_view.sql`

## Flags and open questions

- **Run Time / # Completed are exploratory, not confirmed.** These are reconstructed from job operation timestamps as our best guess at what the sheet's "Run Time" and "# Completed" columns mean — nobody has verified this against a real finished bottling job yet, because none has run on the test tenant so far.
- **Not built:** which sales rep is tied to the order, bottle/lid size and color, and fill weight — the underlying Plex data for these either doesn't have a confirmed link or needs a unit-conversion step nobody has done yet.
- **The sheet's 4 sub-tabs (Liquids/Powders/Gummies/Capsules) aren't split out** — this report returns all Bottling activity in one list. Splitting by product type would need a confirmed way to tell those categories apart in Plex, which doesn't exist yet.

## More detail

[`spreadsheets/bottling_job_schedule.md`](../../spreadsheets/bottling_job_schedule.md) has the full column-by-column mapping and research history.
