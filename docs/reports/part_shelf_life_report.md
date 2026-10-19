# Vox Nutrition Item List with Shelf Life Details

> **Status:** 🔬 Built 2026-10-19, checked on PlexTest data (35,370 rows, 15,701 parts), not yet deployed · **Category:** Production · **Runs:** with Audit - Part Info and Routing (same pipeline, `part_routing`)

## What this tells you

Every part, with the shelf life configured on it: the type (Best By, Use By,
Sell By), the length, and the unit. It exists to check that **shelf life is set
up on every item that needs it**, and to find the ones that are missing.

## Where it fits

It replaces the Plex SQL Development Environment report of the same name,
created on 2025-04-02 ("for getting an item list with shelf life details to
validate shelf life configuration is enabled for all items as appropriate").
It is the third of the three stored-procedure reports, and shares a pipeline
with [Audit - Part Info and Routing](part_info_routing_report.md).

## How it's built (high level)

Every part from the part master, joined to its shelf-life records and to the
shelf-life type names, exactly as the Plex query does. Parts with no shelf life
are kept, with the shelf-life columns empty.

## What a row is

There is **one row per part per shelf-life record**:
- A part configured with Best By, Use By and Sell By appears **three times**.
- A part with **no shelf life appears once**, flagged `shelf_life_missing = true`.

On PlexTest, 2026-10-19:

| shelf_life_type | rows |
|---|---|
| Best By | 15,667 |
| Use By | 9,839 |
| Sell By | 9,836 |
| (none: no shelf life configured) | **28** |

## Things to know before trusting it

- **`shelf_life_missing` replaces the Plex query's commented-out filter**
  (`WHERE SL.Shelf_Life IS NULL`, "to see items missing the shelf life").
  Filter on it in Looker instead of editing SQL.
- **Count parts, not rows.** To count parts, count distinct part number +
  revision, because most parts appear once per shelf-life type.
- **Every part is included,** whatever its status or type, as in Plex.
  Obsolete parts and raw materials are in it; filter on `part_status` or
  `part_type` if needed.
- **Freshness.** It refreshes with its pipeline. An edited shelf-life value is
  seen by the change probe, which sums the values.

## Columns

`part_no`, `part_rev`, `part_name`, `part_type`, `shelf_life_type`,
`shelf_life`, `shelf_life_units`, `part_status`, `shelf_life_missing`.

## Technical pointers

- SQL: `reports/sql/part_shelf_life_view.sql`.
- Config: the third `bq_view` in `reports/part_routing.yaml` (and
  `reports/test/part_routing.yaml`). `Part_v_Part_Shelf_Life` is paged by
  `Part_Shelf_Life_Key`.
