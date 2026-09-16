# Monday Board Catalog — "Tablero nuevo" (personal dev test board)

**Board:** Tablero nuevo · **ID:** `18430931138` · **Account:** Emilio's personal
Monday developer sandbox (`MONDAY_API_KEY_PERSONAL_DEV` in `.env`) — **not**
the Voxnutrition company workspace.

This board's column *structure* was built to mirror the real prod board
("Design & QA", `18395121955` — see
[`monday_board_catalog.md`](monday_board_catalog.md)) closely enough to test
the new standalone Label Design push service against something realistic,
without touching prod or the shared "Plex Import Board" test board while
permissions there are unresolved (see `sep-14-brief-and-pending-items.md`).

**Regenerating this:**

```graphql
query {
  boards (ids: [18430931138]) {
    name
    columns { id title type settings_str }
  }
}
```

using `MONDAY_API_KEY_PERSONAL_DEV`, or `scripts/replicate_board_columns.py`
(see below) to re-sync structure from prod.

## Built with `scripts/replicate_board_columns.py`, 2026-09-16

Copies column title+type (+status/dropdown labels) from a source board onto
a target board via the Monday API. Two real bugs found and fixed while
building this catalog — **worth remembering for any future Monday
column-creation script**:

1. **`create_column`'s `defaults` argument for a `status` column must be a
   dict keyed by string index** (`{"labels": {"0": "A", "1": "B"}}`), the
   same shape `settings_str` itself returns on read — **not a bare array**
   (`{"labels": ["A", "B"]}`). The array form is silently accepted (the
   mutation still returns a column id, no error) but produces a column with
   a single **null**-labeled option; the real label text is dropped with no
   warning. This is genuinely dangerous: 39 status columns were created
   looking successful before this was caught by reading `settings_str` back
   and finding every one had null labels — the API's success response alone
   does not mean the data landed.
2. **`create_column` cannot set more than ~20 labels in one call.** Between
   20 and 24 labels it starts failing outright with `InvalidColumnSettingsException:
   Invalid Settings` — confirmed by bisection, not content-related (every
   individual label text was independently valid). There is no
   `change_column_metadata` property for labels (`ColumnProperty` enum is
   only `title`/`description`), and setting an item's value to a
   not-yet-existing label text does **not** auto-create it
   (`change_column_value` errors `missingLabel` instead). **No clean API
   path exists to add labels to a status column beyond the first ~20** —
   confirmed via GraphQL schema introspection of the mutation type; the two
   `*_managed_column` mutations that looked promising are for Monday's
   custom-app column-type SDK, unrelated to native status columns.

Also caught mid-build: title-only dedupe (skip creating a column if the
*title* already exists on the target) isn't enough when the target has a
same-titled column of a **different type** left over from earlier manual
setup — this board already had plain-`text` "Reason Code" and "Bottle
Material" placeholders from the old Code.gs `MONDAY_COLUMNS` map, which
silently blocked the real `status` versions from being created. Fixed by
hand: the two empty text placeholders were deleted and replaced with the
real status columns; the "Sales Rep" text placeholder had one real value
(`"Taylor Wach"`) so it was renamed to "Sales Rep (legacy text)" instead of
deleted, and the two real prod "Sales Rep" columns (status rep-list +
people) were added fresh alongside it.

## Reason Code — deliberately incomplete, by decision not oversight

Prod's real "Reason Code" status column has 33 options (`monday_board_catalog.md`
— by far its most granular field, full of historical near-duplicates). Since
Monday's API caps a new status column at ~20 labels and there's no way to
add more, and since `label_design_service/reason_code.py` only ever needs to
address 6 specific option texts, this test board's "Reason Code" column
holds **only those 6**, re-indexed 0–5 (indices do **not** match prod's):

| Index (this board) | Label | Prod's real index |
|---|---|---|
| 0 | Customer Initiated: Label Edit | `[105]` |
| 1 | Customer initiated: Label review | `[0]` |
| 2 | New label design (Vox design) | `[1]` |
| 3 | New label review (Customer design) | `[2]` |
| 4 | Vox Initiated: Label Edit/Review | `[106]` |
| 5 | 3D Rendering | `[4]` |

**Whatever code pushes to Monday must look up the real index by label text
per-board** (query `settings_str`, don't hardcode index numbers) — this was
already true across prod vs. any test board (Code.gs's own comments say the
same), but is doubly true here since even the option set differs, not just
the numbering.

## Full column list (59 total)

Status/dropdown columns' full label lists are in each column's
`settings_str` (see the regenerate query above) — omitted here since they're
verbatim copies of the equivalent section in `monday_board_catalog.md`,
except **Reason Code** (see above) and any prod formula/subitems columns,
which could not be created via the API (formula text references
board-internal column ids that don't carry over; subitems are Monday-managed
automatically) — skipped, not attempted:

- `Label SKU` (`name`, the item's own title column, already exists on every board)
- `Design Total Days`, `QA Total Days`, `Days Total` (`formula`)
- `Subitems` (`subtasks`)

Everything else from prod's 61-column list exists here too, either
pre-existing (from the earlier Code.gs `MONDAY_COLUMNS` setup — `LCR`
`text_mm76tgzp`, `Memo` `long_text_mm76j9e7`, etc.) or freshly created by
`replicate_board_columns.py` this session. Query the board directly for the
authoritative id list; this file documents *what happened*, not a
point-in-time id dump that will drift.
