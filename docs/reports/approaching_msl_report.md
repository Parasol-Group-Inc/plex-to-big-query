# Inventory | Approaching MSL

> **Status:** 🛠 Built 2026-10-26, validated on PlexProd, deploy pending. NetSuite fallback built 2026-10-26, needs the two app tables first (see below) · **Category:** Supply Chain · **Runs:** rides the Sales Orders pipeline

## What this tells you

Which parts are at or approaching their reorder point (minimum inventory), how many days of stock are left, and whether more is on order or being made. It rebuilds Jennilyn's "Approaching MSL" Google Sheet.

## Columns

- **reorder_point:** NetSuite's reorder point when the manual-data app has one for the part, otherwise the part's Minimum Inventory Quantity in Plex (rule `reorder_source`). `plex_reorder_point` and `ns_reorder_point` show both.
- **on_hand_qty / quantity_available:** available is on hand minus sold demand minus the demand finished goods will pull through their bills of materials. **It goes negative on purpose**: it means open orders need more than is in stock. Same figure as the Out of Stock report.
- **at_reorder_point:** available is at or below the reorder point.
- **avg_daily_usage:** Plex's figure once it rests on enough days, otherwise NetSuite's. Plex works it out from recorded production times each component's BOM quantity, over the last 90 days or since Plex's first production, whichever is shorter (`usage_days`); Plex stores no average itself. **usage_source** says which one you are looking at (`Plex`, `NetSuite`, `Plex (short history)`), and `plex_avg_daily_usage` / `ns_avg_daily_usage` show both.
- **days_on_hand / days_to_reorder:** stock divided by daily usage. A negative days_to_reorder means the part is already past its reorder point by that many days of usage.
- **on_order_qty / open_job_qty / in_mfg_or_ordered:** open purchase orders, and open jobs making the part.

## NetSuite fallback and the rules behind it

Plex has days of production history where NetSuite has years, so until Plex catches up the report borrows NetSuite's average daily usage and reorder point. They are typed in, by CSV upload, on the **MSL inputs** tab of the Manual Data app, and the thresholds are on its **MSL rules** tab. The tab shows the four rules as inputs with the value in effect filled in; change one and save, and only changed rules are recorded (the defaults below apply until then):

| Rule | Default | What it does |
|---|---|---|
| `usage_min_days` | 30 | Days of Plex history before Plex's usage replaces NetSuite's |
| `reorder_source` | ns | Whose reorder point wins when both exist (`ns` or `plex`). A NetSuite 0 counts as "none set" |
| `disagree_pct` | 25 | Flag a part when Plex and NetSuite usage differ by more than this % |
| `stale_days` | 45 | Flag NetSuite figures older than this many days |

**data_flag** lists, per part, every reason to look twice: negative availability (intended), usage taken from NetSuite or from a very short Plex history, Plex and NetSuite disagreeing, stale NetSuite figures. Empty when there is nothing to say.

NetSuite numbers legacy items (13041) where Plex says `33041-00VOXNU-0`. A NetSuite row only reaches the report once it carries the exact Plex part number. The first upload fills 534 by a naming rule and marks them **guessed**: they need a person to confirm them. Items with no Plex match are kept and marked, not dropped.

**Before this view can be created in a dataset, the two app tables must exist** (the view fails to create without them, and that looks like a broken view). Run once per dataset, then the app's first push replaces them with the same schema:

```sql
CREATE TABLE IF NOT EXISTS `voxdatalake.PlexProd.msl_item_inputs` (ns_item_id STRING, part_no STRING, description STRING, ns_avg_daily_usage FLOAT64, ns_reorder_point FLOAT64, as_of_date DATE, mapping_status STRING, note STRING, updated_by STRING, updated_at TIMESTAMP, is_deleted BOOL);
CREATE TABLE IF NOT EXISTS `voxdatalake.PlexProd.msl_rules` (rule STRING, value STRING, note STRING, updated_by STRING, updated_at TIMESTAMP, is_deleted BOOL);
```

## Flags and open questions

- **Plex production history starts 2026-10-18**, so Plex usage rests on about 8 days for now. Until it reaches `usage_min_days` the NetSuite figure is used where there is one.
- **NetSuite and Plex reorder points differ a lot** (33001: 9.19M in NetSuite vs 4.30M in Plex). Jennilyn to say which is right; the default follows NetSuite because her sheet did.
- The sheet's creatine figure implied about 297 a day where this NetSuite export says 371: probably a different averaging window. Ask Jennilyn which window her sheet used.
- The report shows two rows for some part numbers (different Part_Key, e.g. 12009-01VOXNU-1). That predates the NetSuite fallback and is not yet explained.
- Parts with no recorded production show no usage, so no days figures. Raw powders consumed outside recorded production appear this way.
- Pipeline: `reports/sales_orders.yaml` (and test copy) → `approaching_msl_report`; SQL `reports/sql/approaching_msl_view.sql`. No Plex SQL Developer copy: it depends on BigQuery views.
