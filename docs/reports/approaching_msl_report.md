# Inventory | Approaching MSL

**One row per part number.** Plex keeps up to four internal records for many parts: one is the stocked record, the others are "wrappers" that let a recipe use the part in another unit (for example grams instead of kilos). The report converts the wrappers into the stocked record's unit and counts each part once. Demand is taken from the stocked record only, because Plex already copies every wrapper's demand onto it. If two NetSuite items are the same material and map to one Plex part, their usage is added together.

**Every part with a reorder point is listed, even with nothing in stock and nothing on order** (since 2026-10-28). Until then those parts, the most urgent ones, were missing.

> **Status:** ✅ Live in PlexProd since 2026-10-27, NetSuite inputs loaded. Unit and coverage fix, part type columns, demand_qty and Plex-only reorder point 2026-10-28 (see Flags). · **Category:** Supply Chain · **Runs:** rides the Sales Orders pipeline

## What this tells you

Which parts are at or approaching their reorder point (minimum inventory), how many days of stock are left, and whether more is on order or being made. It rebuilds Jennilyn's "Approaching MSL" Google Sheet.

## Columns

- **reorder_point:** the part's Minimum Inventory Quantity in Plex. Plex only since 2026-10-28 (Jennilyn's call); `ns_reorder_point` still shows NetSuite's figure for reference.
- **on_hand_qty / quantity_available:** available is on hand minus sold demand minus the demand finished goods will pull through their bills of materials. **It goes negative on purpose**: it means open orders need more than is in stock. Same figure as the Out of Stock report.
- **demand_qty:** the demand that available subtracts: on_hand_qty − demand_qty = quantity_available. It is what open orders and jobs for *parent* items will consume of this part. Not the same as open_job_qty, which is jobs *making* this part (incoming supply). Added 2026-10-28.
- **at_reorder_point:** available is at or below the reorder point. A part with no reorder point (0 in Plex) is flagged only when available is negative, i.e. open orders need more than is in stock (since 2026-10-28; before, 23 parts with nothing set and nothing due were flagged).
- **avg_daily_usage:** Plex's figure once it rests on enough days, otherwise NetSuite's. Plex works it out from recorded production times each component's BOM quantity, over the last 90 days or since Plex's first production, whichever is shorter (`usage_days`); Plex stores no average itself. **usage_source** says which one you are looking at (`Plex`, `NetSuite`, `Plex (short history)`), and `plex_avg_daily_usage` / `ns_avg_daily_usage` show both.
- **days_on_hand / days_to_reorder:** stock divided by daily usage. A negative days_to_reorder means the part is already past its reorder point by that many days of usage.
- **on_order_qty / open_job_qty / in_mfg_or_ordered:** open purchase order deliveries, and open jobs making the part. A delivery already marked Received is left out; a partly received one counts in full and is flagged, because Plex does not say how much of it arrived.
- **unit / product_type:** the unit every quantity on the row is in (the stocked record's; blank in Plex for most raw materials, which are kilos), and the Plex product type, for filtering out labels or bottles.
- **part_type / part_group / part_group_key / part_source_key:** Plex's part type (Finished Goods, Raw Materials, ...), part group (Capsule, Label, Raw Ingredient, Packaging, ...) and source, for filtering the list. Taken from the stocked record. Added 2026-10-28 from Jennilyn's `approaching_msl_report_v2`, which this replaces.

## NetSuite fallback and the rules behind it

Plex has days of production history where NetSuite has years, so until Plex catches up the report borrows NetSuite's average daily usage (and, until 2026-10-28, its reorder point). They are typed in, by CSV upload, on the **MSL inputs** tab of the Manual Data app, and the thresholds are on its **MSL rules** tab. The tab shows the four rules as inputs with the value in effect filled in; change one and save, and only changed rules are recorded (the defaults below apply until then):

| Rule | Default | What it does |
|---|---|---|
| `usage_min_days` | 30 | Days of Plex history before Plex's usage replaces NetSuite's |
| `reorder_source` | — | No longer read (2026-10-28): the reorder point is always Plex's. The app still shows it |
| `disagree_pct` | 25 | Flag a part when Plex and NetSuite usage differ by more than this % |
| `stale_days` | 45 | Flag NetSuite figures older than this many days |

**data_flag** lists, per part, every reason to look twice: negative availability (intended), usage taken from NetSuite or from a very short Plex history, Plex and NetSuite disagreeing, stale NetSuite figures, partly received purchase orders. Empty when there is nothing to say.

NetSuite numbers legacy items (13041) where Plex says `33041-00VOXNU-0`. A NetSuite row only reaches the report once it carries the exact Plex part number. The 2026-10-27 upload holds 603 filled in by a naming rule and marked **guessed**: they need a person to confirm them. Items with no Plex match are kept and marked, not dropped.

**Before this view can be created in a dataset, the two app tables must exist** (the view fails to create without them, and that looks like a broken view). Run once per dataset, then the app's first push replaces them with the same schema:

```sql
CREATE TABLE IF NOT EXISTS `voxdatalake.PlexProd.msl_item_inputs` (ns_item_id STRING, part_no STRING, description STRING, ns_avg_daily_usage FLOAT64, ns_reorder_point FLOAT64, as_of_date DATE, mapping_status STRING, note STRING, updated_by STRING, updated_at TIMESTAMP, is_deleted BOOL);
CREATE TABLE IF NOT EXISTS `voxdatalake.PlexProd.msl_rules` (rule STRING, value STRING, note STRING, updated_by STRING, updated_at TIMESTAMP, is_deleted BOOL);
```

## Flags and open questions

- **Jennilyn's answers (2026-10-28):** reorder point from Plex only (done); at reorder point after open-order demand (already so); no capsules-only default, she splits the dashboard by part type; average daily usage stays NetSuite's until Plex takes over. Her "Vox Inventory Demand" dashboard showed `open_job_qty` as "Demand": use `demand_qty`.
- **`approaching_msl_report_v2` (Jennilyn's copy, 2026-10-27) should be retired.** It added the filter columns above to the 10-27 version of this view and missed the 10-28 fixes: it counts stock on a part's second Plex record twice (12277-01VOXNU-1: 3,996 available against 3,701 on hand) and leaves out parts with no stock. Use this report's new columns instead. On 2026-10-28 it matched this report on 960 of 995 shared parts (its Available to Sell input was fixed); it still sums wrapper keys wrongly on the other 35.
- **Compared with the Approaching MSL Google Sheet (2026-10-28).** The sheet covers 105 items, almost all stock formula capsules (13xxx). 68 are in the report; 52 of those agree on at reorder point. The 16 that don't: older stock figures in the sheet (7), demand from open orders, which the sheet does not subtract (5), a NetSuite reorder point of 0, which the sheet treats as "no reorder point" and the report replaces with Plex's minimum (4). The sheet flags at `<`, the report at `<=` (kept: at or below is the usual reorder rule, and it differs on only 4 parts). 35 of its items have no NetSuite row in the MSL inputs (mostly the "13xxx - Blend" items).

- **Plex production history starts 2026-10-18**, so Plex usage rests on about 10 days (2026-10-28). It takes over from NetSuite automatically around 2026-11-16. Until it reaches `usage_min_days` the NetSuite figure is used where there is one.
- **Reorder point is Plex's only (2026-10-28).** NetSuite and Plex differed a lot (33001: 9.19M vs 4.30M); Jennilyn chose Plex. 15 parts changed flag.
- The sheet's creatine figure implied about 297 a day where this NetSuite export says 371: probably a different averaging window. The sheet's daily averages were pulled from NetSuite (Jennilyn, 2026-10-28); Plex is to take over.
- **Fixed 2026-10-28: demand was counted twice for 352 parts**, once on the stocked record and once on its wrapper, and for gram wrappers in mixed units (riboflavin read 135 kg on hand minus 17.8 kg minus 17,762 g). 39 parts showed at their reorder point wrongly. Plex usage for gram wrappers was in grams against stock in kilos, which would have broken days on hand when Plex usage takes over.
- **Labels and bottles: are they in scope?** Listing every part with a reorder point added 438 parts with nothing in stock, mostly Product Labels (217) and Stock Labeled Bottles (131). All are at their reorder point. Answered: in scope, split by part type on the dashboard (`part_type`, `part_group`).
- **NetSuite usage unit.** The upload carries no unit; the report assumes NetSuite uses the same unit as Plex's stocked record (kilos for powders). Usage now agrees within 2x for most parts, but a few still differ by 10x or more (e.g. 33008 Caralluma capsules), which may be the short Plex history or a unit difference.
- Parts with no recorded production show no usage, so no days figures. Raw powders consumed outside recorded production appear this way.
- Pipeline: `reports/sales_orders.yaml` (and test copy) → `approaching_msl_report`; SQL `reports/sql/approaching_msl_view.sql`. Plex SQL Developer copy (Plex-side figures only, not yet run in Plex): `reports/plex_sql/approaching_msl_view.sql`.
