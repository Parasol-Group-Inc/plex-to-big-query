# Part Lot Attribute Specs

> **Status:** ✅ Live 2026-10-21 · **Category:** Quality · **Runs:** with Part Lot Inheritance (same pipeline, `part_lot`)

## What this tells you

The Plex screen **Part > Part Lot Attributes** for every active part at once:
each attribute a lot of that part must record, its group, how it is entered,
the passing values or limits, the test method, and how it prints on the COA.
It is for checking that specs are set up consistently across parts, without
opening each part in Plex.

## Where it fits

Requested by Jennilyn on 2026-10-21 ("I need a table of these in BigQuery. Most
parts have a table like this attached to them"). Its companion,
[Part Lot Inheritance](part_lot_inheritance_report.md), shows where each part
takes its lot number, Best By date and attributes from.

## How it's built (high level)

Every active attribute on every active part, joined to the attribute's
template (which gives its name, group and sort order), its display type, its
list, numeric or text specification, its test method and its COA setting. All
of it is pulled from Plex and joined in BigQuery.

## What a row is

**One row per active part per active lot attribute**, in the screen's order
(`sort_order`). On PlexTest, 2026-10-21: 150,027 rows over 7,431 parts. Part 12149-01VOXNU-1
Rev 00 has 33 rows there; its screen showed 34 on the same day, to be checked
against prod.

## Things to know before trusting it

- **Active parts only** (`Part_Status = 'Active'`), and only active attribute
  rows. Plex keeps each retired version of an attribute as an inactive row;
  those are left out.
- **`success_values`** are the passing answers for a list attribute, joined
  with " | ". For a numeric attribute it shows the limits instead, as
  `<= high | => low | target x`. `fail_values` lists the failing answers.
- **Always the same in Plex today:** `target_value` (no numeric spec has a
  target), `test_method_reference` (0), `test_method_required` (true) and
  `note` (blank). Checked against the raw Plex tables on 2026-10-21; they are
  kept in case Plex starts using them.
- **`attachment`** says "Required" for a Document attribute whose test method
  is required. Plex works this out on screen; no field stores it.
- **`inherited_from`** names the component the part takes this attribute from,
  if any. See the inheritance report for the part-level view.
- **`template_active = false`** marks an attribute whose template has been
  retired in Plex but is still attached to the part. Worth reviewing.
- **Freshness.** It refreshes with its pipeline. The spec tables only record
  when a row was added, so an edit in place shows up after the 4 AM full run.

## Columns

`part_no`, `part_rev`, `part_name`, `part_type`, `part_group`, `sort_order`,
`lot_attribute_code`, `attribute_group`, `display_type`, `reference`,
`success_values`, `fail_values`, `default_value`, `low_tolerance`,
`high_tolerance`, `target_value`, `unit`, `test_method`,
`test_method_reference`, `test_method_required`, `coa_display`, `attachment`,
`mandatory`, `note`, `inherited_from`, `template_active`,
`part_lot_attribute_key`.

## Technical pointers

- Config: `reports/part_lot.yaml` (test: `reports/test/part_lot.yaml`)
- SQL: `reports/sql/part_lot_attribute_specs_view.sql`
- Plex SQL Developer version, for spot checks:
  `reports/plex_sql/part_lot_attribute_specs_view.sql`
