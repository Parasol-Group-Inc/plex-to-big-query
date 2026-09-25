# Vox Scorecard | Shipping Revenue (detail)

> **Status:** ✅ Built and verified 2026-09-01 — 1 real shipped line: 17,000 units, $25,500 · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

One row per shipped part per shipment: what shipped, to whom, when, for how much, and its part group — sorted by invoice date. This is Vox's real definition of revenue, given directly by Jennilyn Tockstein (data scientist) in a requirements meeting: *"the shipping revenue should just be the units that went out the door, the summed value of the units that went out the door."*

## Where it fits

The foundation for the Vox Nutrition Scorecard's Revenue tiles, replacing `Vox_Looker_DB - Rev_MTD`/`Vox_Looker_DB - Revenue` (Sheets) and `vw_sales` (a BigQuery view previously fed by a Monday.com sync). See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Pulls from Plex's Shipping module — `Sales_v_Shipper` (the shipment header) joined to `Sales_v_Shipper_Line` (one row per part on that shipment), filtered to shipments whose status is actually "Shipped." Value is `Quantity × Price` off the shipment line itself, not a computed order-value proxy. Invoice date comes from `Sales_v_Shipper_AR_Invoice`, and part group from Plex's Part Group lookup (`Part_v_Part_Group`; see the 2026-09-24 fix below).

- **Pipeline:** `reports/sales_orders.yaml` → `shipping_revenue_report`
- **SQL:** `reports/sql/shipping_revenue_report.sql`

## Flags and open questions

- **⚠ Fixed 2026-09-24 — part group was always blank ("(no group)").** The view joined `Part_v_Part.Part_Group_Key` to `Part_v_Part_Product_Group`, a different lookup that is **empty in test and prod** — so every row read NULL, even though virtually every part has a `Part_Group_Key`. The real lookup is **`Part_v_Part_Group`** (13 groups: Capsule, Softgel, Tablet, Gummy, Powder, Liquid, Label, Packaging, Component, Raw Ingredient, Semi-Finished Goods, Inspection, Supplies); all 10 key values in use on `Part_v_Part` (test and prod) resolve against it. It is newly extracted into `raw_Part_v_Part_Group` by the Sales Orders pipeline, so **group names only appear after the next `terraform apply` + Sales Orders ETL run** — until then the table doesn't exist and the view can't be recreated. Fixed on branch `dev-sandbox`, not deployed. Found by the scorecard sandbox.
- **This whole Plex module was never used by this pipeline before 2026-09-01.** Tree-confirmed via the full schema catalog, then live-confirmed the same day: real data came back and reconciled exactly (17 real `Sales_v_Shipper_Container` rows of 1,000 units each summed to the line's 17,000-unit quantity).
- **Boolean convention differs from the rest of this pipeline.** `Sales_v_Shipper_Status.Shipped` uses `1 = true`, not the `-1 = true` convention already confirmed elsewhere (`Part_v_Container.Active`, etc.) — checked against real rows before writing this, not assumed.
- **`Shipment_Price` (an alternate price field) was 0** on the one real row, while `Price` was populated ($1.50) — `Price` is treated as primary; `Shipment_Price` is exposed as a secondary column, likely an unused override field.
- ~~**Part group came back blank** for the one real shipment — the shipped part has no `Part_Group_Key` assigned on this tenant yet.~~ Wrong diagnosis, corrected 2026-09-24: the part had a key; the view joined the wrong (empty) lookup. See the fix above.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation. [`docs/reports/sales_revenue_summary_report.md`](sales_revenue_summary_report.md) rolls this up by month for the scorecard's single-number tiles.
