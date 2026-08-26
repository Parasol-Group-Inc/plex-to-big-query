# MFG Job Schedule - Inventory Availability (partial)

> **Status:** ✅ Built and deployed 2026-08-26, verified live (0 rows, benign) · **Category:** Production · **Runs:** rides the Part On-Hand Inventory pipeline, 4 PM / 5 PM UTC (prod/test)

## What this tells you

One row per part: its description, how much is currently on hand, and how much is on order from open purchase orders. This covers the 3 columns of the manually maintained "MFG Job Schedule" spreadsheet's "Inventory Availability" tab that Plex can actually answer today.

## Where it fits

Partial coverage of the **Inventory Availability** tab tracked in [`spreadsheets/mfg_job_schedule_inventory_availability.md`](../../spreadsheets/mfg_job_schedule_inventory_availability.md), one of the still-🔍-Mapped sub-tabs of the MFG Job Schedule spreadsheet (see [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md)'s tab tracker). Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Reuses two already-deployed reports directly rather than re-extracting anything: on-hand quantity per part from the Part On-Hand Inventory report, and total quantity on order per part from the Open Purchase Orders report, joined by part number.

- **Pipeline:** `reports/part_on_hand_inventory.yaml` → `mfg_job_schedule_inventory_availability_report`
- **SQL:** `reports/sql/mfg_job_schedule_inventory_availability_view.sql`

## Flags and open questions

- **Only 3 of the tab's ~13 columns are covered.** Reorder Point, Avg Daily (usage rate), Current QTY Available, % Left, Days on Hand, Days to Reorder Point, and Reorder Point Days on Hand are all deliberately left out — their formulas are confirmed exact ratios, but the inputs they depend on (`Avg Daily`, and the allocation/committed-quantity netting logic behind `Current QTY Available`) have no confirmed Plex source. Every plausible candidate table was checked live and is either the wrong shape or confirmed empty on this tenant — see the spreadsheet doc for the full research trail before assuming any of these can be approximated.
- **Currently 0 rows — expected, not broken.** Same benign reason as every other report on this tenant: the underlying on-hand/open-order data hasn't started accumulating real rows yet.
- **"On Order" sums quantity across all open PO lines/releases for a part** — it does not distinguish by due date or supplier, matching the grain of the existing Open Purchase Orders report.

## More detail

[`spreadsheets/mfg_job_schedule_inventory_availability.md`](../../spreadsheets/mfg_job_schedule_inventory_availability.md) has the full column-by-column mapping and research history, including why `Avg Daily`/`Reorder Point`/`Current QTY Available`'s netting logic are treated as genuinely open (not guessed at).
