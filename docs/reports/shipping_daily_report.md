# Vox Scorecard | Shipping Daily (Packages/Orders/Revenue)

> **Status:** ✅ Built and verified 2026-09-01 — 2026-09-01: 17 packages, 1 order, $25,500 shipped · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

For each day: how many packages/cartons shipped, how many distinct orders shipped, how many units, and how much revenue. A new ask, not on the original dashboard — Jennilyn Tockstein (data scientist) described it directly: *"they used to show the number of cartons that they shipped every day... you should be able to pull the number of packages shipped, and then a count of the orders that shipped."*

## Where it fits

New capability for the Vox Nutrition Scorecard's Operations section. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Rolls up `Sales_v_Shipper`/`Sales_v_Shipper_Line` (filtered to actually-Shipped shipments) by ship date, counting distinct shipments as "orders shipped" and joining `Sales_v_Shipper_Container` rows for a real cartons-shipped count.

- **Pipeline:** `reports/sales_orders.yaml` → `shipping_daily_report`
- **SQL:** `reports/sql/shipping_daily_report_view.sql`

## Flags and open questions

- **Live-verified with real, internally-consistent data**: 1 real shipment on 2026-09-01, 17 real container rows (1,000 units each), reconciling exactly to that shipment's 17,000-unit line — the "17 packages shipped" figure is a genuine count, not an estimate.
- **Boolean convention**: `Sales_v_Shipper_Status.Shipped` uses `1 = true` — see [`shipping_revenue_report.md`](shipping_revenue_report.md) for the full note.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
