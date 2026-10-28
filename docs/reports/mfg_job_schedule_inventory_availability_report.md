# MFG Job Schedule - Inventory Availability (partial)

> **Status:** ✅ Built and deployed 2026-08-26. One-row-per-part fix 2026-10-28 (see flags) · **Category:** Production · **Runs:** rides the Part On-Hand Inventory pipeline, prod 1 PM / 6 PM / 11 PM probe + 4 AM full (`PlexOps.etl_schedule`), test nightly

## What this tells you

One row per part: its description, how much is currently on hand, and how much is on order from open purchase orders. This covers the 3 columns of the manually maintained "MFG Job Schedule" spreadsheet's "Inventory Availability" tab that Plex can actually answer today.

## Where it fits

Partial coverage of the **Inventory Availability** tab tracked in [`spreadsheets/mfg_job_schedule_inventory_availability.md`](../../spreadsheets/mfg_job_schedule_inventory_availability.md), one of the still-🔍-Mapped sub-tabs of the MFG Job Schedule spreadsheet (see [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md)'s tab tracker). Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Re-extracts nothing. On-hand comes from the Part On-Hand Inventory report. On order is read from the same Plex purchasing tables as the Open Purchase Orders report, with the same "open" rule, per Plex record. Both are converted into the part's stocked unit and added up per part number. Since 2026-10-28 every part with stock or an open purchase order is listed.

- **Pipeline:** `reports/part_on_hand_inventory.yaml` → `mfg_job_schedule_inventory_availability_report`
- **SQL:** `reports/sql/mfg_job_schedule_inventory_availability_view.sql`

## Flags and open questions

- **Only 3 of the tab's ~13 columns are covered.** Reorder Point, Avg Daily (usage rate), Current QTY Available, % Left, Days on Hand, Days to Reorder Point, and Reorder Point Days on Hand are all deliberately left out — their formulas are confirmed exact ratios, but the inputs they depend on (`Avg Daily`, and the allocation/committed-quantity netting logic behind `Current QTY Available`) have no confirmed Plex source. Every plausible candidate table was checked live and is either the wrong shape or confirmed empty on this tenant — see the spreadsheet doc for the full research trail before assuming any of these can be approximated.
- **Fixed 2026-10-28 (code review).** A part with more than one Plex record (Plex keeps "wrapper" records that let a recipe use the part in grams, for example) showed one row per record, each repeating the part's full on-order quantity. It is now one row per part number, with the wrapper records converted into the stocked unit. Parts on order with nothing in stock were missing (27) and are now listed. Deliveries already marked Received are left out. About 2,030 rows in PlexProd.
- **"On Order" sums quantity across all open PO deliveries for a part.** It does not split by due date or supplier. A partly received delivery counts in full, as in the Open Purchase Orders report.
- **Units:** on order is in the purchase order's unit, which is assumed to be the part's stocked unit. Not checked against Plex's unit conversions.

## More detail

[`spreadsheets/mfg_job_schedule_inventory_availability.md`](../../spreadsheets/mfg_job_schedule_inventory_availability.md) has the full column-by-column mapping and research history, including why `Avg Daily`/`Reorder Point`/`Current QTY Available`'s netting logic are treated as genuinely open (not guessed at).
