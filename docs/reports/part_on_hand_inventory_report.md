# Part On-Hand Inventory

> **Status:** ✅ Built and deployed 2026-08-11, enriched 2026-08-21 — compiles and runs cleanly but not yet proven against real inventory quantities · **Category:** Supply Chain · **Runs:** own pipeline, 9:20 PM / 9:30 PM Mountain (prod/test)

## What this tells you

One row per part, showing how much of it is physically on hand right now — total quantity across all its storage containers, plus a count of how many containers make up that total — along with the part's number, name, and product-type classification (Vitamin, Mineral, Botanical Extract, Stock/Custom Formula, etc.). This is the Plex-native replacement for the "Available Inventory" number tracked by hand on the "MFG Job Schedule" Google Sheet, and it also feeds the newer Inventory Risk Analysis report.

## Where it fits

Covers the **Available Inventory** column referenced across several tabs of the **MFG Job Schedule** Google Sheet (tracked in [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md), with the deepest dive in [`spreadsheets/mfg_job_schedule_inventory_availability.md`](../../spreadsheets/mfg_job_schedule_inventory_availability.md)) — also listed in [`reports-list/supply-chain.md`](../../reports-list/supply-chain.md), which flags a Google Sheet called **Approaching MSL** as the likely current manual source of this same number and a good candidate for a side-by-side comparison once its real content is available. The **Inventory Risk Analysis** report, added as a sibling view on this same pipeline, builds on this one to flag aging/slow-moving stock.

## How it's built (high level)

Adds up every storage container's quantity for a part, counting only containers that are marked active and whose status is a "good" one (excludes containers on hold, quarantined, or otherwise flagged) — then attaches the part's name, number, and product-type category. On-hand inventory in this Plex system turned out to live under the Part module rather than the more obviously-named Warehouse module, which had been the first guess.

- **Pipeline:** `reports/part_on_hand_inventory.yaml` -> `part_on_hand_inventory_report`
- **SQL:** `reports/sql/part_on_hand_inventory_view.sql`

## Flags and open questions

- **Verified to compile and run, not yet verified against real quantities.** The underlying container data was empty on the test tenant when this was built and deployed, so the report is confirmed to query cleanly end-to-end, but the on-hand numbers it will produce haven't been checked against any known-correct quantity yet.
- **"Available Inventory" and "Current QTY Available" on the sheet may not be the same number this report produces.** Research into the sheet's own "Inventory Availability" tab found that its "Current QTY Available" is a different, smaller number than raw on-hand quantity — likely on-hand minus some allocated/committed amount. Several plausible Plex sources for that netting logic were checked directly and all came back empty on the test tenant (not ruled out, just unconfirmed one way or the other). Until that's resolved, this report should be read as **raw physical on-hand quantity**, not necessarily the exact "available to promise" number the sheet shows.
- **The sheet's other related figures — Reorder Point, Avg Daily usage, Days on Hand, Days to Reorder Point — are not built here.** No Plex source was found for the daily-usage rate or reorder point after checking every plausible candidate table; these most likely come from NetSuite or a separate demand-planning source outside this pipeline.

## More detail

[`spreadsheets/mfg_job_schedule_inventory_availability.md`](../../spreadsheets/mfg_job_schedule_inventory_availability.md) has the full formula research and the open netting-logic question. [`docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md`](../MFG_JOB_SCHEDULE_BUILD_PLAN.md) has the build narrative, including how the Warehouse-vs-Part module question was resolved.
