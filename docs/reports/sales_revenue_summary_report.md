# Vox Scorecard | Revenue Summary (MTD/YTD)

> **Status:** ✅ Rebuilt and verified 2026-09-01 (corrected source module) — September 2026: $25,500 shipping revenue, 17,000 units · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

One row per (month, part group): how much shipping revenue Vox actually recognized — the dollar value of units that physically went out the door — and how many units that covers. Built to answer the Vox Nutrition Scorecard's "MTD Revenue" and "$28.7M YTD" tiles.

## Where it fits

Replaces `Vox_Looker_DB - Rev_MTD`, `vw_sales`, and `vw_sales_mtd_vs_goal`. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md) for the full mapping.

## How it's built (high level)

This report was rebuilt the same day it was first written. The original version computed revenue from Sales orders (price × released quantity). In an actual requirements meeting with Jennilyn Tockstein (the data scientist — see `meetings-reference/Sep-1/`), she was explicit that's the wrong source: *"the shipping revenue should just be the units that went out the door... the sales one I think will be less reliable since it will not count in when we close things short or ship partials."* This report now rolls up `shipping_revenue_report` (built on Plex's Shipping module — `Sales_v_Shipper`/`Sales_v_Shipper_Line`, filtered to actually-Shipped shipments) by month and part group instead.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_revenue_summary_report`
- **SQL:** `reports/sql/sales_revenue_summary_view.sql` (reads `shipping_revenue_report`, same pipeline)

## Flags and open questions

- **⚠ Fixed 2026-09-24 (upstream) — "Revenue by part group" was always one bar, "(no group)".** This view's own SQL is unchanged; the `part_group` it groups by comes from `shipping_revenue_report`, which joined the wrong, empty lookup (`Part_v_Part_Product_Group`) instead of `Part_v_Part_Group`. Fixed there and **deployed 2026-09-25**; the groups show in PlexTest now, and in PlexProd from the first scheduled Sales Orders run after the deploy (the run that first extracts `raw_Part_v_Part_Group` there). See [`shipping_revenue_report.md`](shipping_revenue_report.md).
- **The name is now slightly stale** — still says "sales_revenue" even though the source is Shipping. Kept the same name deliberately (replace in place, not a second dead view) — a rename is a cosmetic cleanup for later.
- **Live-verified with real data**: September 2026, 1 shipment, 17,000 units, $25,500. Part group came back `(no group)` for that shipment — at the time put down to a missing `Part_Group_Key`; corrected 2026-09-24, it was the wrong lookup table (see the fix above).
- **`Sales_v_Shipper_Status.Shipped` uses `1 = true`**, not the `-1 = true` convention used elsewhere in this pipeline — confirmed by checking the real status rows before writing this, not assumed.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation. [`docs/reports/shipping_revenue_report.md`](shipping_revenue_report.md) is the detail-grain report this one rolls up.

## Where the data came from

*Added 2026-11-10.* Every row carries three columns that say where its data came from and how current it was:

| Column | Meaning |
|---|---|
| `data_source` | `odbc` (Plex's database feed, the normal case) or `live` (read from Plex's own screens because the database feed was behind) |
| `data_as_of` | for `odbc`, the newest change the feed had delivered; for `live`, when the screens were read |
| `data_label` | the two in words, e.g. "ODBC, data to 11-10 11:56 MT" or "Plex screens, read 11-10 13:20 MT" |

They come from `PlexOps.data_freshness`, group **revenue and shipments**. An old `data_as_of` on a working day means the feed has stopped, even if every run succeeded (as on 2026-11-10). See [data_freshness.md](data_freshness.md).

