# Vox Scorecard | Cycle Count Accuracy

> **Status:** ✅ Deployed 2026-09-11 · 🔧 date fix 2026-09-22, per-location accuracy fix 2026-09-24 (deployed 2026-09-25) · **Category:** Supply Chain · **Runs:** rides the Part On-Hand Inventory pipeline, 9:20 PM / 9:30 PM Mountain (prod/test)

## What this tells you

How accurate the warehouse's cycle counts were, month by month. Each location counted in a month is judged **once** — on its latest count that month — as either right (nothing unaccounted for) or wrong, and `accuracy_pct` is the share that were right. That is Vox's own definition: a per-location hit rate, deliberately blind to how much stock sat in each location.

Alongside it: `locations_counted` (how many locations were judged — exactly the number the percentage is taken over), `items_counted` (every count performed, recounts included, so the effort still shows), and `recounted_locations` (how many locations were counted more than once that month; only their latest count is judged).

## Where it fits

The Vox Scorecard's **"Cycle count accuracy"** tile. Also the Warehouse department's one "Cycle Count" entry in the Reports List ([`reports-list/warehouse.md`](../../reports-list/warehouse.md)). Scope and the three numbers the warehouse tracks — locations counted, items counted, accuracy — were confirmed with Jennilyn on 2026-09-11.

## How it's built (high level)

Reads Plex's cycle-count records (`Part_v_Cycle_Inventory`, extracted to `raw_Part_v_Cycle_Inventory`). Cycle counting lives under Plex's **Part** module, not the Warehouse module where you'd expect it. Each count is dated and assigned to its month; within each month and location only the latest count is kept for the accuracy figures, while the count totals include every count. One row per month, newest first.

A quantity-weighted accuracy (`accuracy_pct_qty_weighted`) and Plex's own per-count accuracy (`avg_plex_accuracy`) are kept beside the tile's figure as cross-checks. The tile doesn't use them — but if the weighted figure is noticeably lower than `accuracy_pct`, the misses are concentrated in the locations holding the most stock.

- **Pipeline:** `reports/part_on_hand_inventory.yaml` → `part_cycle_count_report`
- **SQL:** `reports/sql/part_cycle_count_view.sql`

## Flags and open questions

- **No location names.** Plex stores the counted location as a number, and no location list is extracted from Plex yet, so the report can say *how many* locations were counted and how many missed, but not *which* ones by name.
- **An empty month is normal, not 0%.** Counting is lumpy by design — as Vox put it on 2026-09-11, "they go through periods where they do a whole lot and where they don't do anything." A month with no counts simply has no row. Check `locations_counted` before showing a percentage.
- **⚠ Don't cite PlexTest's earlier "82.1%".** That September figure came from test rows injected to prove the tile worked, not from real counts. Those rows were deleted on 2026-09-24, so expect the test data to be empty or near-empty until real counts are recorded in Plex.
- **Fixed 2026-09-22 — the report couldn't be queried at all.** Plex's count date arrives in a numeric format the old SQL couldn't convert, so every query against the report errored. It had been mistaken for "no counts yet". The date is now converted the same way as everywhere else in the pipeline.
- **Fixed 2026-09-24, deployed 2026-09-25 — accuracy was averaged per count, not per location.** A location counted twice in a month weighed double, and the location that gets recounted is usually the one that missed, so misses were over-weighted. Now each location counts once a month, on its latest count. In the scorecard sandbox, May moved from 92.5% to 94.1%.
- **Per-part accuracy targets aren't used yet.** Plex carries an accuracy threshold per part (`Part_v_Cycle_Frequency`, already extracted), but how it links to the counts can't be confirmed until there are real counts to look at.

## More detail

[`docs/SCORECARD_SANDBOX_FINDINGS.md`](../SCORECARD_SANDBOX_FINDINGS.md) (finding 6), [`reports-list/warehouse.md`](../../reports-list/warehouse.md), and `CHANGELOG.md` entries for 2026-09-11, 2026-09-22 and 2026-09-24. The SQL file header records every definition decision.
