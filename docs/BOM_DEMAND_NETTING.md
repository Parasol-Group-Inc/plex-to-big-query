# BOM demand netting: how component demand is calculated

*Written 2026-10-30. Applies to `inventory_available_to_sell_report`, and through it to
`approaching_msl_report` and `inventory_out_of_stock_report`. The SQL lives in
`reports/sql/inventory_available_to_sell_view.sql`, section "Netted component demand".*

## In one paragraph

A component's demand is what its parent items still need to **make**, not what they
**sell**. Demand passes down the bill of materials one level at a time, and at each level
the part's own stock is subtracted first. Only the shortfall goes down to the next
level. This is standard MRP netting. Jennilyn described the rule ("go down one BOM at a
time and only bring over demand for things not stocked") and supplied the worked example
below. Both numbers are published:
- **netted demand**, used for availability, reorder point and out of stock;
- **gross demand**, the old full explosion, kept because Jennilyn finds it useful ("I've
  never been able to see total demand for any component + that demand reduced by bottled
  inventory").

## Why it changed

Until 2026-10-30 every open sales order was multiplied straight down Plex's
pre-flattened BOM (`Part_v_Flat_BOM`) to every component at every depth. Stock held at
the levels in between was ignored, so a finished good already on the shelf still created
demand for its bright bottle, and again for the capsules that fill it. Approaching MSL therefore
**double-counted demand** whenever an intermediate level had stock: Jennilyn's report,
2026-10-30.

## The worked example (Jennilyn's, reproduced on PlexProd)

Nutricost Inositol 240ct. Jennilyn's note called it the "Nutricost blend"; the part at
the bottom of her chain, 33312-00NUT46-0, is the capsule (Plex name "Capsule | Nutricost -
NTC Inositol (Capsule) Target Wt. 655mg"), 241 per 240-count bottle. Below it the BOM
continues to the blend and raw materials; the same netting carries on there.

| Part | BOM line | On hand | Old (gross) demand | Netted demand | Passes down |
|---|---|---|---|---|---|
| 93312-00NUT46-0 finished good (FG) | (sold) | 40,944 | 50,000 ordered | 50,000 ordered | 50,000 − 40,944 = **9,056** |
| 53312-00NUT46-0 bright bottle (BB) | 1 per 93312 | 0 | 50,000 | **9,056** | 9,056 |
| 73312-00NUT46-0 label | 1 per 93312 | 5,778 | 50,000 | **9,056** | 3,278 |
| 33312-00NUT46-0 capsule | 241 per 53312 | 0 | 50,000 × 241 = **12,050,000** | 9,056 × 241 = **2,182,496** | … |

The old figure for the capsule was 5.5 times the real need.

## The rule, precisely

For every part, processed so that a part comes after all of its parents:

```
gross(part)     = own open order demand
                + SUM over each single-level BOM parent:  shortfall(parent) × BOM quantity
shortfall(part) = GREATEST(gross(part) − netting stock(part), 0)
```

- **Own open order demand:** open sales-order releases, quantity minus shipped, for
  statuses Plex marks `Include_In_MRP` (Pending Fulfillment and Hold). This is the same
  `order_demand` as before.
- **BOM quantity:** from the single-level `Part_v_BOM` (component quantity per one unit of
  the direct parent), active lines with a positive quantity.
- **Netting stock:** the part's available on-hand. That is `part_on_hand_inventory_report`,
  Vox's rule: active containers in OK, Hold, Inspection Required or Hold for Design Order.
  Stock held on the part's wrapper keys is added, converted (see Wrappers).
- **Published netted component demand:** `gross − own order demand`, i.e. what reached the
  part from its parents.

### Processing order: low-level codes

A part can sit at different depths under different parents. Before netting it, every
parent must already be netted. Each part gets a **low-level code** (`bom_low_level_code`):
its **deepest** depth anywhere in the BOM, found by a recursive walk over `Part_v_BOM`.
A part that is nobody's component is 0. Parts are netted in that order.

PlexProd, 2026-10-30:

| Low-level code | Parts |
|---|---|
| 0 | 7,107 |
| 1 | 7,305 |
| 2 | 372 |
| 3 | 267 |
| 4 | 467 |
| 5 | 394 |
| 6 | 55 |

There are no cycles: the walk is capped at depth 20 and the deepest part is at 6.

## How the SQL does it, and why it looks the way it does

```
bom_edge   single-level Part_v_BOM: parent_key, component_key, qty
bom_walk   recursive: every path down the BOM (depth per path)
bom_llc    MAX(depth) per part = low-level code
bom_node   one row per part in the BOM or with orders: llc, own demand, netting stock
net_0 … net_6   unrolled netting stages; net_k holds every part with llc <= k
netted_demand   gross − own demand per part (0 on wrapper keys)
```

**Why seven unrolled stages, not one recursive CTE.** Netting level k needs the shortfall
of parents at *every* lower level, summed. BigQuery's recursive CTE only sees the previous
iteration's rows and cannot both carry earlier levels forward and aggregate them, so the
stages are written out, one per level.

**Why each stage reads the previous one only once.** BigQuery does not store a CTE's
result: a CTE referenced twice is computed twice. The first draft read `net_(k-1)` twice
per stage (once to carry rows forward, once to join), so the work doubled at every level,
2^6 re-runs of the whole chain, and the test query ran past two minutes before it was
cancelled. Each stage now unnests every netted row into itself plus one contribution per
BOM line, then groups by part. That is one read per stage, and the whole view runs in
about 12 seconds.

**Deeper than six levels.** If Plex ever gets a BOM deeper than the stages cover, that
part is not netted. It keeps the gross figure, so it overstates rather than reading zero,
and `bom_depth_beyond_netting` is TRUE. Add a `net_7` stage (copy `net_6`, change both
numbers) and point `netted_demand` at it.

## Wrappers (unit-conversion keys)

Plex keeps up to four Part_Keys per part number. The extra ones ("wrappers") let a recipe
use the part in another unit. Each wrapper has one BOM line to the stocked key, and that
line's quantity is the conversion factor (1, 0.001 for grams, 0.000001 for milligrams).
See WRAPPER KEYS in the view.

In netting, a wrapper **nets nothing itself** (netting stock 0). It passes its whole demand
down its BOM line, multiplied by the factor, to the stocked key. The stocked key nets that
against its own stock plus all wrapper stock, converted. The wrapper's own row reports 0
component demand, as before: the stocked key carries it. Approaching MSL takes demand from
the stocked key only, unchanged.

## Columns

`inventory_available_to_sell_report`:

| Column | Meaning since 2026-10-30 |
|---|---|
| `order_demand_qty` | the part's own open order demand (unchanged) |
| `component_demand_qty` | **netted**: what parents pass down after their own stock |
| `total_demand_qty` | order + netted component demand |
| `available_vs_total_demand` | on hand + wrapper stock − total demand (netted) |
| `gross_component_demand_qty` | **new**: the old flat explosion, no netting |
| `bom_low_level_code` | **new**: deepest BOM depth, 0 to 6 |
| `bom_depth_beyond_netting` | **new**: TRUE if deeper than the stages; that part keeps gross |
| `component_demand_from_held_orders_qty` | still **gross**: Hold is a slice of order demand with no meaningful netted share |

`approaching_msl_report`:

| Column | Meaning |
|---|---|
| `demand_qty` | **netted**; `on_hand_qty − demand_qty = quantity_available` |
| `gross_demand_qty` | **new**: order + gross component demand, i.e. what `demand_qty` was before 2026-10-30 |

## Effect on PlexProd, 2026-10-30

- **Available to sell:** same 2,882 rows. Component demand went down on 737 parts and up
  on none. Parts short (`available_vs_total_demand < 0`) went from 997 to 786.
- **Approaching MSL:** `gross_demand_qty` equals the old `demand_qty` on all 1,445 parts.
  Demand went down on 585 parts. **85 parts are no longer at their reorder point**
  (848 → 763), and none newly reached it.

## How to check it yourself

Jennilyn's chain, which should read 9,056 / 9,056 / 2,182,496:

```sql
SELECT part_no, bom_low_level_code, on_hand_qty, order_demand_qty,
       gross_component_demand_qty, component_demand_qty, available_vs_total_demand
FROM `voxdatalake.PlexProd.inventory_available_to_sell_report`
WHERE REGEXP_CONTAINS(part_no, r'^[9753]3312-00NUT46') AND NOT is_unit_wrapper
ORDER BY part_no DESC
```

Invariants that must hold, each expected to return 0:

```sql
SELECT
  COUNTIF(component_demand_qty > gross_component_demand_qty + 0.001) AS netted_above_gross,
  COUNTIF(is_unit_wrapper AND component_demand_qty != 0)             AS wrapper_with_demand,
  COUNTIF(bom_depth_beyond_netting)                                  AS too_deep
FROM `voxdatalake.PlexProd.inventory_available_to_sell_report`
```

## Tracking it over time

The views only show today. `PlexProd.msl_demand_daily` keeps one row per part per day
(America/Denver date), filled by the `msl_demand_daily` scheduled query every day at
13:00 UTC, after the 4 AM MT full run. SQL: `terraform/msl_demand_daily.sql`. Columns:
`stock_qty`, `order_demand_qty`, `gross_component_demand_qty`,
`netted_component_demand_qty`, `covered_by_stock_qty` (gross − netted: demand already
covered by stock higher up), `available_qty`, plus `reorder_point` / `at_reorder_point`
from Approaching MSL when the part is in it. About 2,850 rows a day. First row:
2026-10-30.

```sql
SELECT snapshot_date, gross_component_demand_qty, netted_component_demand_qty,
       covered_by_stock_qty, stock_qty
FROM `voxdatalake.PlexProd.msl_demand_daily`
WHERE part_no = '33312-00NUT46-0'
ORDER BY snapshot_date
```

## What it still does not do

- **Open jobs.** Demand is sales orders only, as before. A job already making a bottle is
  not counted as covering it, and a job's own material requirements (`Part_v_Job_Bom`) are
  not demand here. Adding them needs care: a job is created from an order, so the same
  demand could appear twice.
- **Time.** Netting is a point-in-time total. Stock is applied to all open demand at once,
  not to the earliest due date first.
- **Which parent gets the stock.** When a part has several parents, its stock nets the
  summed demand, not each parent's share. That is standard MRP, and it is why only totals
  per part are published.
- **Plex SQL copies are ported but untested.** `reports/plex_sql/` available-to-sell and
  out-of-stock carry the same netting in T-SQL (recursive CTE for low-level codes, the
  seven stages with `CROSS APPLY (VALUES …)` in place of `UNNEST`). Neither has been run
  in Plex SQL Developer (OPEN_ITEMS D13). If it rejects the recursive CTE, take the
  low-level code from `Part_v_Flat_BOM` instead: `MAX(BOM_Level)` per
  `Component_Part_Key`. The approaching MSL copy never computed demand; it points at the
  available-to-sell copy.
- **Open jobs and due dates** are tracked as OPEN_ITEMS D26.

## History

- 2026-09-09: flat-BOM explosion built. Vox BOMs were one level deep then, so gross and
  netted were the same.
- 2026-10-28: wrapper keys fixed (demand on stocked keys only, wrapper stock converted).
- 2026-10-30: netting, after Jennilyn found the MSL double count. CHANGELOG 2026-10-30,
  PR #103, deployed `deploy/2026-10-30T1555Z`. Plex SQL copies ported the same day.
