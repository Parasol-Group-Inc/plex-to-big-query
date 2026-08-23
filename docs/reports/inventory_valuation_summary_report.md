# Vox | Inventory Valuation Summary

> **Status:** ✅ Built and deployed 2026-08-10/11, join chain and business intent both confirmed against live data · **Category:** Inventory · **Runs:** `plex-etl-inventory-snapshot` job, 8:40 PM / 8:50 PM Mountain (prod/test)

## What this tells you

One row per part per costing snapshot, showing that part's total standard cost at that point in time — a rolled-up dollar value per part, not a line-by-line cost breakdown. This is the NetSuite-parity replacement for the "Vox | Inventory Valuation Summary" report.

## Where it fits

Maps to the **Vox | Inventory Valuation Summary** report tracked in the NetSuite parity list — see [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md). It's built and deployed together with its sibling report, **Current Inventory Snapshot** (the detail version of the same data), because both come from the same underlying costing data pulled once per run.

## How it's built (high level)

Plex periodically takes a "snapshot" of every part's standard cost, broken down into several cost components (material, labor, overhead, etc.). This report takes that same snapshot data and sums all the cost components together for each part, so instead of seeing five or six cost lines per part you see one total dollar value per part per snapshot — the summary view of the same numbers the detail report (Current Inventory Snapshot) shows line-by-line.

- **Pipeline:** `reports/inventory_snapshot.yaml` -> `inventory_valuation_summary_report` (second view built from the same extraction as `inventory_snapshot_report`)
- **SQL:** `reports/sql/inventory_valuation_summary_view.sql`

## Flags and open questions

- **This is a standard-cost valuation, not a physical on-hand count.** The underlying data comes from Plex's Advanced Standard Costing engine — it values each part at its standard cost, not "quantity on hand x cost." This was flagged as a semantic risk during build but has since been **confirmed with the report requester**: the standard-cost snapshot is the right data, and sourcing physical on-hand quantity separately is not needed.
- **Cost sub-type detail is not broken out here.** The individual cost components (material vs. labor vs. overhead, etc.) that make up each part's total are visible in the sibling detail report (Current Inventory Snapshot) but are collapsed into one number in this summary. Those components carry an internal Plex code with no confirmed human-readable label yet — if a future request needs "how much of this part's cost is labor vs. material," that label lookup would need to be found first.
- **Snapshot frequency:** Plex takes these cost snapshots roughly hourly, so this report can show the same part's valuation shifting slightly between snapshots on the same day — that's expected, not a data error.

## More detail

See [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md) for how this maps to the NetSuite report list, and [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) (item #73, plus #15/#74 for the shared join chain) for the full research and confirmation history.
