# Part Lot Inheritance

> **Status:** ✅ Live 2026-10-21 · **Category:** Quality · **Runs:** with Part Lot Attribute Specs (same pipeline, `part_lot`)

## What this tells you

The **Lot Management** box on each part in Plex, for every active part: whether
a lot is required, the lot format, and where the part takes its **lot number**,
**Best By date** and **lot attributes** from. It is for finding gaps and parts
whose settings don't line up (Jennilyn, 2026-10-21: "only for active parts ...
just a table so we can see gaps and ensure things are lining up").

## Where it fits

Companion to [Part Lot Attribute Specs](part_lot_attribute_specs_report.md),
which lists the attributes themselves.

## How it's built (high level)

Every active part, joined to its inventory settings, its lot format, and the
three kinds of lot inheritance Plex stores per part: lot number overrides,
Best By date inheritance and attribute inheritance. Each component is shown
the way the screen shows it, "part no-revision name".

## What a row is

**One row per active part**: 15,694 on PlexTest, 2026-10-21. Nearly every part is Active (7 Obsolete, 5 Initial Setup), and about half have no lot attributes of their own. Checked against Plex on 2026-10-21:

| Part | Lot No | Best By | Attributes |
|---|---|---|---|
| 93001-00VOXNU-0 | 53001-00VOXNU-0 | 53001-00VOXNU-0 | Multiple (all from 53001) |
| 93056-BKVOXNU-1 | Generate | None | None |

## Things to know before trusting it

- **`lot_no_inheritance = 'Generate'`** means the part has no lot number
  override, so Plex builds the number from the lot format.
- **`attribute_inheritance`** shows the component when exactly one attribute is
  inherited, and "Multiple" when more are, as the screen does, even when they
  all come from the same component. `attribute_from_part_nos` names them.
- **`lot_no_matches_best_by = false`** is the main "not lining up" check: the
  lot number and the Best By date come from different components, or only one
  of them is inherited.
- **`own_lot_attribute_count = 0`** on a part that should carry specs is a gap.
- **Open question:** 93001 counts 14 inherited attributes here and 13 on its
  screen. The likely cause is one retired template still listed; to be checked.
- **`lot_format`** is the format's name as Plex lists it (e.g. `AABYYMMDD`,
  `PreWeigh`); blank when the part has none (5,917 parts in prod).
- **Freshness.** It refreshes with its pipeline.

## Columns

`part_no`, `part_rev`, `part_name`, `part_type`, `part_group`, `lot_required`,
`lot_replenishable`, `lot_format`, `lot_no_inheritance`,
`lot_no_from_part_nos`, `best_by_inheritance`, `best_by_from_part_nos`,
`attribute_inheritance`, `attribute_from_part_nos`,
`inherited_attribute_count`, `own_lot_attribute_count`,
`lot_no_matches_best_by`.

## Technical pointers

- Config: `reports/part_lot.yaml` (test: `reports/test/part_lot.yaml`)
- SQL: `reports/sql/part_lot_inheritance_view.sql`
- Plex SQL Developer version, for spot checks:
  `reports/plex_sql/part_lot_inheritance_view.sql`
- **Prod schedule, after the first deploy.** Prod runs come from
  `PlexOps.etl_schedule`, not Terraform, so the new job runs only once these
  rows exist:

  ```sql
  INSERT INTO `voxdatalake.PlexOps.etl_schedule`
    (job_name, run_time, mode, enabled, note, updated_by, updated_at)
  VALUES
    ('plex-etl-part-lot', '13:52', 'probe', TRUE, 'part_lot', 'emilio', CURRENT_TIMESTAMP()),
    ('plex-etl-part-lot', '18:52', 'probe', TRUE, 'part_lot', 'emilio', CURRENT_TIMESTAMP()),
    ('plex-etl-part-lot', '23:52', 'probe', TRUE, 'part_lot', 'emilio', CURRENT_TIMESTAMP()),
    ('plex-etl-part-lot', '04:52', 'full',  TRUE, 'part_lot', 'emilio', CURRENT_TIMESTAMP());
  ```
