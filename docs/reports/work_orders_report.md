# Work Orders

> **Status:** ✅ Built and deployed 2026-07-13 · **Category:** Production · **Runs:** `plex-etl-work-orders` / `plex-etl-work-orders-test`, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per production step — which job, which part, which workcenter it ran on, how much was planned to run there, and (once operators start logging time against it) how many hours were actually spent, split into productive time versus downtime from a problem event (a jam, a material shortage, an injury, etc.). It's the shop-floor activity feed for every job moving through the plant, and it's this pipeline's oldest and most foundational report — several other reports (MFG Job Schedule, Labeling/Printing Open Work Orders) are built by adding more columns to this same underlying data rather than starting over.

A naming note worth knowing: Plex has a separate object literally called "Work Order," but it isn't connected to the day-to-day shop-floor records (Jobs) that carry real production data — there's no link between the two in the data Plex exposes. This report is named "Work Orders" for the business (that's the concept people mean when they ask "what's running and what's it done"), but under the hood it's built entirely from Jobs and Job Operations, not Plex's own Work Order object.

## Where it fits

This is an original, internal deliverable of this pipeline — it doesn't replace a specific NetSuite report or a manually maintained Google Sheet, and it has no entry of its own in [`reports-list/production.md`](../../reports-list/production.md). It exists because the plant needed a Plex-native view of job activity, and it became the shared foundation other reports now ride on top of (see [`reports-list/production.md`](../../reports-list/production.md) for how MFG Job Schedule and the Labeling/Printing Open Work Orders reports build on it).

## How it's built (high level)

Starts from every job operation (one row per workcenter step within a job), attaches the job's own identity and the part being made, adds the workcenter's name and type, and adds up how many hours operators have logged against that step — separated into normal production time and time lost to a logged problem. Planned setup/run time (from the job's routing) sits alongside actual logged hours so the two can be compared once there's enough real activity to make that comparison meaningful. Job and operation-level dates (due, started, completed, created) come along for scheduling and lead-time questions.

- **Pipeline:** `reports/work_orders.yaml` → `work_orders_report`
- **SQL:** `reports/sql/work_orders_view.sql`

## Flags and open questions

- **Status columns are numeric keys, not readable text.** The Plex lookup table that would translate a job/operation status number into a label ("Released," "In Process," etc.) had no records in the test environment when this was built, so `job_status_key` and `job_op_status_key` come through as raw numbers. They're kept so the report can still be filtered on, but reading them requires knowing Plex's own key values until that lookup table is populated and a join is added.
- **Real production data is still filling in.** At build time (2026-07-13), the underlying Job, Job Operation, and hour-logging tables were empty on both Plex tenants, so planned-vs-actual comparisons couldn't be checked against anything real. The test tenant has since started seeing real jobs — some genuine data appeared there over the following weeks — but that hasn't been specifically re-confirmed against this report's own numbers, and production had not yet shown real job activity as of the most recent check on record.
- **Downtime-hours split assumes every logged event is a problem.** The productive-vs-downtime split relies on a confirmed-but-narrow observation (every hour-log row tied to an "event" was a problem event, not some other kind) — reasonable given what's been seen so far, but worth another look once more logging volume exists.

## More detail

No spreadsheet or NetSuite doc exists for this one — see [`docs/TECHNICAL_REFERENCE.md`](../TECHNICAL_REFERENCE.md) for how this pipeline's shared extraction and multiple report views fit together, and `CHANGELOG.md` for the build and verification history.
