# MFG Job Schedule

> **Status:** ✅ Built and deployed 2026-08-11, enriched 2026-08-21 — several columns still awaiting real production data to confirm · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per manufacturing job step — part and quantities, which workcenter/room/equipment it ran on, who worked it, lot number, and the most recent QC checksheet result for that step. It also carries a first attempt at a couple of "goal met?" checks (yield and turnaround time) mirroring the tracker's own scoring. This is the Plex-native replacement for the "Open" tab of the manually maintained "MFG Job Schedule" Google Sheet.

## Where it fits

Fulfills the **"Open"** tab of the **MFG Job Schedule** Google Sheet tracked in [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md) — also listed in [`reports-list/production.md`](../../reports-list/production.md). It's the general-purpose parent report that [Bottling Job Schedule](bottling_job_schedule_report.md) is a Bottling-specific sibling of. Two other tabs/columns of the same sheet are covered by separate reports: NC numbers by `quality_nonconformance_report`, and on-hand inventory by `part_on_hand_inventory_report`.

## How it's built (high level)

Starts from the same Job/Job Operation data as Work Orders, then adds the columns that sheet doesn't need: job status in plain text, the operator's name (resolved from the employee list), lot number and manufacture date, the latest QC inspection result for that step, equipment/asset ID, building/room, and a real Vitamin/Mineral/Stock-vs-Custom product classification. It also computes two early "did this job hit its goal" flags copied from the sheet's own Success-tab rules: whether output quantity met the 95%/92% (stock/custom) yield target, and whether the job finished within 84 days of being created.

- **Pipeline:** `reports/work_orders.yaml` -> `mfg_job_schedule_report`
- **SQL:** `reports/sql/mfg_job_schedule_view.sql`

## Flags and open questions

- **Most joins are confirmed by shape only, not by real matches.** The test tenant had zero rows in the Lot, Equipment, Job Type, and Job Distribution tables when this was built, so the join logic is verified to compile and line up correctly, but not yet proven against real production records. The operator-name join (`Started_By`/`Completed_By` -> employee) is inferred by analogy to a confirmed pattern elsewhere, not literally confirmed either.
- **Yield % and "met goal" columns are exploratory, not the sheet's real Success Rating.** The 95%/92%/84-day thresholds themselves come straight from the sheet's own configuration, but two of the three inputs feeding them are best-guess stand-ins: yield is calculated per job step rather than per whole job (so a multi-step job won't match the sheet's single per-job number), and "days to complete" is measured from the job's creation date in Plex rather than the sheet's manually typed "Date Entered," which has no Plex equivalent at all.
- **Two Stock-vs-Custom "leads" are exposed but superseded.** `job_type` and the job-distribution columns were early, unconfirmed guesses at telling stock from custom orders; a confirmed, already-populated Plex field for this (`part_product_type`) was found afterward and added, but the older speculative columns haven't been removed from this view.
- **QC status is the closest available stand-in, not an exact match.** It reflects the most recent inspection for that job step in general, not specifically "raw material received" testing the way the sheet's own QC columns are worded.
- **Lot shelf-life is passed through as a raw value**, not turned into an expiration date — its data type is confirmed, but what the value actually represents hasn't been checked against real numbers yet.
- **Deliberately not built:** NC/Deviation number tied to a specific job (a real join exists in a separate report as of 2026-08-18 but isn't merged into this one yet), per-capsule dosage specs (needs a unit conversion nobody has done), and the sheet's NetSuite work-order number, Date Entered, Days in WIP, Sign-Off, and free-text Notes columns — none of those exist in Plex at all.

## More detail

[`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md) has the full column-by-column mapping, the running list of open questions for the Data Architect/Scientist, and links to every other tab of the same spreadsheet. [`docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md`](../MFG_JOB_SCHEDULE_BUILD_PLAN.md) has the full technical build narrative.
