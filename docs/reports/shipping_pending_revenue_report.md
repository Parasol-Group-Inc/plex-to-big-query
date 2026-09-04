# Vox Scorecard | Total in Shipping (Pending Revenue)

> **Status:** ✅ Built and verified 2026-09-01 — 1 real pending shipment: 20,000 ready units, $115,800 · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

The dollar value of units that are done and sitting in the shipping module, but haven't left the building yet. Given directly by Jennilyn Tockstein (data scientist): *"this is revenue that is — it's the revenue value of items that are done. They're in shipping, but they haven't left the building yet... they might have 10,000 units ordered, but 5,000 units are ready, and we'd only want the value of the 5,000 units that are ready to ship, not the 10,000 total."*

## Where it fits

Replaces the Vox Nutrition Scorecard's "Total in Shipping"/"Revenue in Shipping" Operational Health tile, and the Flow funnel's "Ready to Ship" phase. Previously fed by `shipping_revenue_daily` (BigQuery, Monday.com-synced). This is a distinct concept from WIP ([`sales_order_value_by_status_report`](sales_order_value_by_status_report.md)) — Jennilyn was explicit these are two different metrics. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Reads `Sales_v_Shipper`/`Sales_v_Shipper_Line` filtered to shipments that exist (units have been picked/packed) but aren't yet "Shipped" and aren't "Canceled" — exactly the "ready" quantity Jennilyn described, not the order's full quantity. Also carries a "blanket order" flag, bridging back through the Release/PO chain to `Sales_v_PO_Type.Blanket`.

- **Pipeline:** `reports/sales_orders.yaml` → `shipping_pending_revenue_report`
- **SQL:** `reports/sql/shipping_pending_revenue_view.sql`

## Flags and open questions

- **Price fallback, decided 2026-09-01.** The one real pending shipment on this tenant has `Shipper_Line.Price = 0` — Plex appears to only finalize this field once a shipment actually ships. Rather than report $0 for everything pending, this view falls back to the customer's base-tier price list whenever the shipment price is 0 or unset. That's an estimate, not the eventual invoiced price — worth a second look once more pending shipments exist to compare against. Without the fallback, this tile would read $0 today.
- **Live-verified**: 20,000 ready units, effective price $5.79 (from the price-list fallback), $115,800 ready value.
- **Boolean convention**: `Sales_v_Shipper_Status` uses `1 = true` — see [`shipping_revenue_report.md`](shipping_revenue_report.md) for the full note.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
