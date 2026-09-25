# Vox | Inventory Valuation Summary

> **Status:** ✅ Built and deployed 2026-08-10/11, join chain and business intent both confirmed against live data · **Category:** Inventory · **Runs:** `plex-etl-inventory-snapshot` job, 8:40 PM / 8:50 PM Mountain (prod/test)

## What this tells you

One row per part per costing snapshot, showing that part's standard cost **per unit** at that point in time — a rolled-up dollar value per part, not a line-by-line cost breakdown. On the most recent snapshot it also shows the quantity on hand today and what that stock is worth (`inventory_value` = on-hand × unit cost). This is the NetSuite-parity replacement for the "Vox | Inventory Valuation Summary" report.

## Where it fits

Maps to the **Vox | Inventory Valuation Summary** report tracked in the NetSuite parity list — see [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md). It's built and deployed together with its sibling report, **Current Inventory Snapshot** (the detail version of the same data), because both come from the same underlying costing data pulled once per run.

## How it's built (high level)

Plex periodically takes a "snapshot" of every part's standard cost. The cost is per unit, kept for each step (operation) of the part's routing, and split into cost components (two on this tenant). This report takes the cost in force on the snapshot date and adds the components together for **one** operation, the part's final one. Each operation's cost already includes the steps before it, so adding operations together would count the same cost twice. The result is one per-unit dollar value per part per snapshot. For the latest snapshot, that is multiplied by the quantity on hand (from the On-Hand Inventory report) to give the stock's value.

- **Pipeline:** `reports/inventory_snapshot.yaml` -> `inventory_valuation_summary_report` (second view built from the same extraction as `inventory_snapshot_report`; also reads `part_on_hand_inventory_report` for quantity)
- **SQL:** `reports/sql/inventory_valuation_summary_view.sql`

## Flags and open questions

- **Fixed 2026-09-24, deployed 2026-09-25.** The per-part cost was wrong. It added every operation's cost together (the real blend `23127-01VOXNU-1` read $4.85 for a part that costs $1.25–$1.35), and it grouped by a cost model that is blank on Plex's snapshot. It now takes one operation's cost: the highest-costed one from the part's most recent cost change. It also works when Plex's snapshot-to-cost link table is empty, which it is in real Plex; the cost then comes from the cost history in force on the snapshot date. New columns: `part_key`, `unit_cost` (the same value as `total_cost`), `costed_operation_key`, `operation_count`, `cost_change_date`, `cost_source`, `is_current_snapshot`, `on_hand_qty`, `inventory_value`. Found by the scorecard sandbox, see [`docs/SCORECARD_SANDBOX_FINDINGS.md`](../SCORECARD_SANDBOX_FINDINGS.md) finding 4.
- **The standard cost is per unit, and Plex's snapshot has no quantity.** Earlier this doc said the requester had confirmed the standard-cost snapshot alone was the right data. That holds for a per-part cost list. It does not hold for a dollar value of stock: that needs quantity × cost, and `Part_v_Snapshot` has no quantity column. Quantity therefore comes from today's containers, and **only the most recent snapshot gets `on_hand_qty` and `inventory_value`**. Earlier snapshots leave them blank rather than pricing today's stock at old costs.
- **"Final operation" is inferred, not read.** Plex's routing (`Part_v_Part_Operation`: operation order and which operations are active) is not extracted. The view uses the highest-costed operation from the part's latest cost change as a stand-in. On real data this correctly skips the blend's operations retired by its 4 Sep 2026 re-routing. Extracting the routing would make it exact. All stock is valued at the final operation's cost, so work part-way through the routing reads slightly high.
- **Cost is per part revision.** Some part numbers exist twice, for example "Rev 00" and "Weighed". A cost on one revision does not value stock held on the other. The Inventory Value Total report counts such uncosted stock (`uncosted_on_hand_part_count`).
- **Cost sub-type detail is not broken out here.** The individual cost components (material vs. labor vs. overhead, etc.) that make up each part's total are visible in the sibling detail report (Current Inventory Snapshot) but are collapsed into one number in this summary. Those components carry an internal Plex code with no confirmed human-readable label yet — if a future request needs "how much of this part's cost is labor vs. material," that label lookup would need to be found first.
- **Snapshot frequency:** this was expected to be roughly hourly. In fact PlexTest holds a single real snapshot (1 Sep 2026, midnight) and PlexProd none. If several appear on one day, each gets its own rows here, and the total report uses the last one of the day.

## More detail

See [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md) for how this maps to the NetSuite report list, and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) (item #73, plus #15/#74 for the shared join chain) for the full research and confirmation history.
