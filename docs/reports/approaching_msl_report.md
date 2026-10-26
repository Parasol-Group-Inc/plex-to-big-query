# Inventory | Approaching MSL

> **Status:** 🛠 Built 2026-10-26, validated on PlexProd, deploy pending · **Category:** Supply Chain · **Runs:** rides the Sales Orders pipeline

## What this tells you

Which parts are at or approaching their reorder point (minimum inventory), how many days of stock are left, and whether more is on order or being made. It rebuilds Jennilyn's "Approaching MSL" Google Sheet.

## Columns

- **reorder_point:** the part's Minimum Inventory Quantity in Plex.
- **on_hand_qty / quantity_available:** available is on hand minus sold demand minus the demand finished goods will pull through their bills of materials. **It goes negative on purpose**: it means open orders need more than is in stock. Same figure as the Out of Stock report.
- **at_reorder_point:** available is at or below the reorder point.
- **avg_daily_usage:** worked out from recorded production times each component's BOM quantity, over the last 90 days or since Plex's first production, whichever is shorter (`usage_days`). Plex stores no average itself.
- **days_on_hand / days_to_reorder:** stock divided by daily usage. A negative days_to_reorder means the part is already past its reorder point by that many days of usage.
- **on_order_qty / open_job_qty / in_mfg_or_ordered:** open purchase orders, and open jobs making the part.

## Flags and open questions

- **Plex production history starts 2026-10-18**, so avg_daily_usage rests on about 8 days for now and will firm up. Compare against the NetSuite figures.
- Parts with no recorded production show no usage, so no days figures. Raw powders consumed outside recorded production appear this way.
- Pipeline: `reports/sales_orders.yaml` (and test copy) → `approaching_msl_report`; SQL `reports/sql/approaching_msl_view.sql`. No Plex SQL Developer copy: it depends on BigQuery views.
