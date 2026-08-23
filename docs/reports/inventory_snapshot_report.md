# Current Inventory Snapshot

> **Status:** ✅ Built and deployed 2026-08-10/11 · **Category:** Inventory · **Runs:** `plex-etl-inventory-snapshot` 8:40 PM / `plex-etl-inventory-snapshot-test` 8:50 PM Mountain

## What this tells you

One row per part per costing snapshot per cost component — for example, "as of this snapshot, Part X's material cost was $12.34, its labor cost was $3.10," and so on. This is the Plex-native parity report for NetSuite's "Current Inventory Snapshot."

**Important:** despite the name, this is a **standard-cost snapshot**, not a physical on-hand quantity count. It shows what Plex's costing engine believes each cost component of a part is worth at a point in time, not how many units are sitting in the warehouse. That's a deliberate, confirmed choice — see "Where it fits" below — not a gap.

## Where it fits

This is the exact NetSuite report this project built parity for, tracked as item **#15** in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md#15--73--74--inventory-snapshot--valuation-summary--transaction--️-resolved). It's also listed in [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md) as one of the NetSuite reports this pipeline already covers.

The report requester confirmed that the standard-cost snapshot is the right data for this report — physical on-hand quantity was considered and ruled out as unnecessary.

This report shares its data and its Cloud Run job with a sibling report, **Vox | Inventory Valuation Summary** (tracked separately in [`inventory_valuation_summary_report.md`](inventory_valuation_summary_report.md)), which totals these same cost components up to one number per part instead of breaking them out line by line. This report is the detail view; that one is the rollup.

## How it's built (high level)

Plex records a cost "snapshot" roughly every hour, and for each snapshot it tracks the individual cost components (material, labor, overhead, etc.) that make up a part's standard cost. Getting from the snapshot down to those actual dollar values takes three hops through Plex's data: the snapshot itself, a pointer table that links a snapshot to a specific cost change, and a history table that resolves that pointer into the real part, cost-component type, and dollar amount. This report walks that chain and attaches each part's number and name for readability.

- **Pipeline:** `reports/inventory_snapshot.yaml` -> `inventory_snapshot_report`
- **SQL:** `reports/sql/inventory_snapshot_view.sql`

## Flags and open questions

- **Cost-component labels aren't resolved yet.** Each row shows a raw numeric code for which cost component it is (material vs. labor vs. overhead, etc.) rather than a readable label — no Plex source with a name-to-code lookup for these could be found. Until one turns up, reading this report means matching the numeric code to a component by cross-referencing Plex directly.
- **Join chain is confirmed live, not just built.** This isn't a caveat so much as a note of confidence: the three-table join this report depends on was tested against real tenant data and came back with matching, non-empty rows every time — it's not resting on an assumption about how the tables relate.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md#15--73--74--inventory-snapshot--valuation-summary--transaction--️-resolved) has the full investigation — how the join chain was discovered, the standard-cost-vs-physical-quantity question and how it was resolved with the report requester, and the still-open cost-component labeling question.
