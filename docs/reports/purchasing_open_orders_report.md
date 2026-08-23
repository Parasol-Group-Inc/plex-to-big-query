# Vox | Open Purchase Orders

> **Status:** ✅ Built and deployed 2026-08-10/11, confirmed live · **Category:** Supply Chain · **Runs:** `plex-etl-purchasing-open-orders`, 7:40 PM / 7:50 PM Mountain (prod/test)

## What this tells you

One row per open purchase order line — which supplier it's going to, what part and quantity, when it's due, and where the PO stands in its approval workflow. "Open" means the PO hasn't been cancelled, denied, or fully received yet, so this is effectively a to-do list of purchasing activity still in flight.

## Where it fits

This is the NetSuite-parity build for the **Open Purchase Orders Report V1** report, tracked in [`reports-list/supply-chain.md`](../../reports-list/supply-chain.md) and logged as item #75 in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md). Plex does have its own built-in screen covering similar ground ("Purchase Order Releases Due"), but that's a UI-only view inside Plex — it can't be queried or exported, so it doesn't replace the need for this report to get the same information into BigQuery.

## How it's built (high level)

Pulls every purchase order and its line-item release schedule from Plex's purchasing data, adds the supplier name and PO type/status labels, and keeps only the lines that are still open — not cancelled, not denied, and not yet received. A companion report, **Purchase Orders to Approve: Results**, reuses this exact same data and just narrows it down to the subset still waiting on approval.

- **Pipeline:** `reports/purchasing_open_orders.yaml` → `purchasing_open_orders_report`
- **SQL:** `reports/sql/purchasing_open_orders_view.sql`

## Flags and open questions

- None known. Every join and status flag this report relies on was verified against live Plex data (not just schema) on 2026-08-10, including the full status workflow (New, Pending Approval, On Order, Approved, Cancelled, Received, Denied) and the "open" rule itself (not cancelled, not received). A test run confirmed it correctly excludes a cancelled test PO.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) (item #75) has the full confirmation log, including the live status-workflow table and join-key research.
