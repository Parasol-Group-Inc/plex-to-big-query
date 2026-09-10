# Part On-Hand Inventory

> **Status:** ✅ Built and verified against real quantities — reconciles exactly with Plex's own Inventory Status Summary screen · **Category:** Supply Chain · **Runs:** own pipeline, 9:20 PM / 9:30 PM Mountain (prod/test)

## What this tells you

One row per part, showing how much of it is physically on hand right now — total quantity across all its storage containers, plus a count of how many containers make up that total — along with the part's number, name, and product-type classification (Vitamin, Mineral, Botanical Extract, Stock/Custom Formula, etc.). This is the Plex-native replacement for the "Available Inventory" number tracked by hand on the "MFG Job Schedule" Google Sheet, and it also feeds the newer Inventory Risk Analysis report.

## Where it fits

Covers the **Available Inventory** column referenced across several tabs of the **MFG Job Schedule** Google Sheet (tracked in [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md), with the deepest dive in [`spreadsheets/mfg_job_schedule_inventory_availability.md`](../../spreadsheets/mfg_job_schedule_inventory_availability.md)) — also listed in [`reports-list/supply-chain.md`](../../reports-list/supply-chain.md), which flags a Google Sheet called **Approaching MSL** as the likely current manual source of this same number and a good candidate for a side-by-side comparison once its real content is available. The **Inventory Risk Analysis** report, added as a sibling view on this same pipeline, builds on this one to flag aging/slow-moving stock.

## How it's built (high level)

Adds up every storage container's quantity for a part, counting only containers that are marked active and whose status is a "good" one (excludes containers on hold, quarantined, or otherwise flagged) — then attaches the part's name, number, and product-type category. On-hand inventory in this Plex system turned out to live under the Part module rather than the more obviously-named Warehouse module, which had been the first guess.

- **Pipeline:** `reports/part_on_hand_inventory.yaml` -> `part_on_hand_inventory_report`
- **SQL:** `reports/sql/part_on_hand_inventory_view.sql`

## Flags and open questions

- **⚠ Fixed 2026-09-04 — this reported 0 rows and the cause was ours, not Plex's.** The filter read `Active = -1 AND OK_Status = -1`; both columns actually hold `1/0`, so it matched nothing while 122 real containers sat in the table. Now returns real data, reconciling exactly with Plex's own Inventory Status Summary screen: **1,164 OK + 2 Hold = 1,166 active containers**.
- **On-hand is now an explicit status list**, per Jennilyn (Sep-4): **Hold, Inspection Required, OK, Hold for Design Order** — excluding **Defective and Expired**. `OK_Status` cannot express that rule: it is 0 on Hold and Inspection Required (which count) and 1 on Allocated/Loaded/Shipped/Staged (which must not, or shipped goods count as on-hand).
- **The Container_Status lookup join was removed.** Plex has 16 statuses including `HOLD FOR DESIGN ORDER`; the extracted copy has 15 and is missing that one. An INNER join would silently drop containers in any status the stale lookup hasn't caught up with.

- **Now matches Plex's own "Inventory Summary" screen column for column** (added 2026-09-09). Amber named that screen as the place to see on-hand; its columns are Part Number / Revision / Description / Containers / Quantity / Weight, and all six are now published here. Weight is the container's **net** weight — not gross, which would include the container's own tare weight. Container locations are published as a set per part, since a part's containers can be spread across several and there is no single "the" location to name.
- **The "Current QTY Available" netting question is answered — it's a separate report now.** Research into the MFG Job Schedule sheet's "Inventory Availability" tab had found its "Current QTY Available" was a smaller number than raw on-hand, probably on-hand minus something committed, with every plausible Plex source coming back empty. The Sep-4 Plex screenshots resolved it: the netting is **sales-order demand**, not allocation, and it now lives in [`inventory_available_to_sell_report`](inventory_available_to_sell_report.md). **Read this report as raw physical on-hand quantity** and that one for available-to-promise — the split is deliberate, so there is one definition of each.
- **The sheet's other related figures — Reorder Point, Avg Daily usage, Days on Hand, Days to Reorder Point — are not built here.** No Plex source was found for the daily-usage rate or reorder point after checking every plausible candidate table; these most likely come from NetSuite or a separate demand-planning source outside this pipeline.

## More detail

[`spreadsheets/mfg_job_schedule_inventory_availability.md`](../../spreadsheets/mfg_job_schedule_inventory_availability.md) has the full formula research and the open netting-logic question. [`docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md`](../MFG_JOB_SCHEDULE_BUILD_PLAN.md) has the build narrative, including how the Warehouse-vs-Part module question was resolved.
