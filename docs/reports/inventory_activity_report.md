# Inventory Activity Detail Usage Per Month

> **Status:** ✅ Built and deployed 2026-08-10/11, one open validation item pending real production data · **Category:** Supply Chain · **Runs:** `plex-etl-inventory-activity` 8:20 PM / `plex-etl-inventory-activity-test` 8:30 PM Mountain

## What this tells you

One row per part per calendar month, showing how much of that part was produced, how much was used up (depleted), and the net change between the two. This is the Plex-native parity report for NetSuite's "Inventory Activity Detail Usage Per Month."

## Where it fits

This is the exact NetSuite report this project built parity for, tracked as item **#29** in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md#29--inventory-activity-detail-usage-per-month--inventory_activity_report--️-resolved). It's also listed in [`reports-list/supply-chain.md`](../../reports-list/supply-chain.md) and [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md) as one of the NetSuite reports this pipeline already covers.

## How it's built (high level)

Plex doesn't actually have a queryable "Inventory Activity" data source — the only thing with that name is a stored procedure the pipeline isn't allowed to use. So instead, this report is built by combining two other Plex data sets that track the same underlying quantities: how much of each part was produced, and how much was consumed, on a given date. Those two are summed up separately by part and by month, then combined into one row per part/month showing production, usage, and the difference between them (net change), with the part number and name attached for readability.

- **Pipeline:** `reports/inventory_activity.yaml` -> `inventory_activity_report`
- **SQL:** `reports/sql/inventory_activity_view.sql`

## Flags and open questions

- **The underlying data comes from a different Plex module than expected, and hasn't been validated against real numbers yet.** The production/depletion data this report is built from actually belongs to Plex's "Advanced Inventory Traceability — Product Genealogy" feature (individual cell/lot tracing), not Plex's own "Inventory Activity" module. Aggregating that data up to part/month plausibly reconstructs the right "usage per month" figures, but this is an inference from how the data is shaped, not a confirmed match to what the report requester expects. **Both source tables were completely empty on the test tenant** at build time, so there was no live sample data to sanity-check actual values against.
- **Needs a follow-up review once real data exists** (test or prod): confirm with the report requester that the produced/depleted/net-change numbers this report generates actually match what "Inventory Activity Detail Usage Per Month" is supposed to show them. This can't be resolved by more querying — it needs a real finished month of activity to look at.
- Aside from that validation gap, the report itself is fully built and has been running cleanly on schedule since deployment.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) has the full investigation — what raw Plex views were considered and ruled out, and the reasoning behind the final data source choice — plus the "Still open" tracker at the bottom for the pending validation item.
