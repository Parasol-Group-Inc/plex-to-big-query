# Scorecard sandbox

A stable BigQuery dataset, **`voxdatalake.ScorecardSandbox`**, holding a full
simulated year (1 Jan 2026 → build day) under every Vox scorecard tile. It
exists to design the Looker Studio report against. What the build found is in
[`docs/SCORECARD_SANDBOX_FINDINGS.md`](../../docs/SCORECARD_SANDBOX_FINDINGS.md).

**Nothing in it is real business data.** Document numbers carry an `SBX`
prefix so a screenshot can't be mistaken for a live figure.

```bash
python scripts/scorecard_sandbox/build.py            # full rebuild, ~7.5 min
python scripts/scorecard_sandbox/build.py --views    # recreate views only
python scripts/scorecard_sandbox/build.py --verify   # rows + month span per view
```

Needs `gcloud auth application-default login` (the org's periodic reauth wall
applies here too), `google-cloud-bigquery` and `pyyaml`. It writes only to
`ScorecardSandbox` — `common.WRITABLE` refuses any other dataset — and reads
PlexTest. It never touches PlexProd.

---

## Why a separate dataset

| | Why it can't host Looker design work |
|---|---|
| **PlexProd** | Almost empty until the 19 Oct cutover. |
| **PlexTest** | Overwritten by every ETL run and wiped nightly, so injected rows are gone by morning. On 2026-09-24 it also held about a month of thin data, and its tables no longer joined each other (see *The snapshot*). |
| **ScorecardSandbox** | Nothing overwrites it. Same view names, same columns. |

A Looker report built here moves to PlexProd by changing the dataset, not the
report.

## The rule it keeps

Set by Emilio, and not negotiable: **no random rows.** Every tile is fed
through the path it will use in production.

- **Plex tiles** read the same views, created from the same `reports/sql/`
  files, over `raw_*` tables shaped exactly like the ETL's. Nothing is ever
  written into a view's output.
- **Every synthetic Plex row is a clone of a real PlexTest row.** The template
  is copied column for column; only keys, dates, quantities and the *real*
  customer, part, rep, work centre or location it points at are changed. So
  every column a view might read arrives as Plex shapes it — including the
  ones nobody knew a view read (`common.Sandbox.clone`).
- **Manual tiles** (goals, safety) read the manual-data app's own tables, with
  the app's own columns.
- **Scale comes from Vox's live scorecard**, not from choice. Every figure in
  [`scale.py`](scale.py) is cited to the 7/31/2026 navigator snapshot or the
  data-mapping workbook in `score-card-reference/`.
- **Costs** exist only because this is a sandbox (approved 2026-09-24). They
  are derived from real prices and real cost ratios, never picked (see
  `inventory.py`).

Where a table has no real row to clone, the module says so in its docstring
and builds the row from a real neighbour instead. The honest list is under
*Where cloning wasn't possible*.

## How a build runs

[`build.py`](build.py), in order:

1. **Dataset.** Created if missing (US).
2. **Base tables.** `scorecard_views()` walks every tile's view in
   `scripts/board/board_data.py` down to its base tables, reading the prod
   YAMLs: 35 views over 53 tables (49 Plex, 4 manual). Each table is
   re-copied from PlexTest, so a rebuild discards the previous build's rows.
   - **Plex tables** come from `SNAPSHOT`, via time travel.
   - **Quality and manual tables** (`COPY_CURRENT`) come as they are now.
   - Rows left by the old `scorecard_test_data.py` injector are stripped.
3. **Generators** ([`generators.py`](generators.py)), in dependency order:
   `manual` → `sales` → `production` → `quality` → `inventory`.
4. **Views.** Created from `reports/sql/`, unless
   [`proposed_sql/`](proposed_sql/) holds a file of the same name (see below).
5. **Verify.** Row count and month span per view. An error and an empty view
   look identical on a dashboard, so both are printed.

Deterministic: each family seeds its own `random.Random(f"{today}-{family}")`,
so two builds on the same day produce the same numbers. A tile that changes
between builds changed because the SQL did.

## The snapshot

`build.SNAPSHOT = "2026-09-23 12:00:00+00"`. Plex tables are read **as they
were at that instant**, not as they are now.

**Why:** PlexTest is written by thirteen pipelines at different times, and
the ETL keeps yesterday's rows when Plex returns none
([`main.py` `write_to_bigquery`](../../main.py)). On the 24th the tenant was
cut back from 182 customers to 24 and from 2,120 priced customer parts to 312,
while the price table kept pointing at the old keys:

| Relation | 23 Sep 12:00 | 24 Sep (live) |
|---|---|---|
| customer part prices → customer parts | 2,119 / 2,119 | 0 / 2,119 |
| customer parts → parts | 2,120 / 2,120 | 312 / 312 |
| jobs → parts | 160 / 160 | 18 / 18 |
| BOM rows → parts | 7,798 / 7,798 | 2,595 / 2,595 |

[`snapshot_check.py`](snapshot_check.py) scores any instant by the foreign
keys the tile views join on:

```bash
python scripts/scorecard_sandbox/snapshot_check.py "2026-09-23 12:00:00+00" now
```

**Time travel reaches back 7 days.** After 2026-09-30 this snapshot is gone,
and the build fails on the copy step. Pick a new instant that scores clean on
every relation, then update `SNAPSHOT`. Never build on one that doesn't.

## The generators

Each module owns a disjoint set of tables and exposes
`generate(sb) -> {table: rows_added}`.

| Module | Writes | Feeds | How it's sized |
|---|---|---|---|
| [`manual.py`](manual.py) | `scorecard_goals_app`, `safety_incidents` | every % to goal; Safe Days | Sales goals: the 68 real goals already imported. Revenue: the legacy company-wide sales goal, as the app held it before 09-24 (unconfirmed, and each row's note says so). Production: the live scorecard's goals, the same every month. Safety: the one real 7/23 recordable. |
| [`sales.py`](sales.py) | 10 `raw_Sales_v_*` tables: order, change, line, release, price, shipper, line, line-release, container, invoice | all Sales and Revenue tiles, WIP, In Shipping, pipeline, Deposit Review | Each rep's real goal × attainment. Rep books are Plex's own `Assigned_To`, and the rep is written on the order in `Inside_Sales`. Real customer parts at real list prices. Orders start 17 Nov 2025, so January has December's bookings shipping. |
| [`production.py`](production.py) | `raw_Part_v_Job`, `_Job_Op`, `_Production` | production vs goal, the three daily reports, FPY, Open Caps, Open Bottles | Live goals × attainment, FPY per group, open backlog to the live 219.7M caps and 1.2M bottles. Jobs are clones of real jobs making the same part, on real lines, recorded by real employees. |
| [`quality.py`](quality.py) | `raw_Quality_v_Problem_2`, deviation tables | NCs, deviations, Destruction $ / Rework $, TAT | The real NCs as templates, at 14–22 a month; deviations at 15–21 a month. Real forms, dispositions and statuses. The real records themselves are never altered. |
| [`inventory.py`](inventory.py) | containers, cycle counts, cell production and depletion, snapshots and cost history; `Minimum_Inventory_Quantity` on 33-parts | quantity available, out of stock, top quantity, average daily usage, valuation, cycle count | Runs last. Stock is sized from the production log and open demand at run time. Out of stock lands on the live 6, computed by running the real availability SQL, not hard-coded. |

Shared plumbing lives in [`common.py`](common.py):

- `Sandbox.clone` copies a template and type-checks every change.
- `Sandbox.when` writes a date in the column's own shape. Plex dates are INT64
  nanoseconds in typed tables and ISO text in tables that were autodetected
  while empty.
- `Sandbox.append` writes through a load job.

Synthetic keys come from one band per family, starting at 9.1 × 10⁹. Real
keys in this tenant are 8 digits, so they can't collide, and a key's band
says which module wrote it.

### Where cloning wasn't possible

Stated so nobody mistakes these for Plex's own shape:

- **`raw_Part_v_Cell_Production` / `_Cell_Depletion`** have never held a real
  row. Each row is a real production record projected onto the columns the two
  tables share, plus its level-1 BOM consumption. Columns nothing real can
  supply are left NULL.
- **`raw_Quality_v_Deviation_Job`** has no real row. It uses the real
  Deviation_Part row's identical four-column shape.
- **`raw_Part_v_Snapshot_Cost_Sub_Type_Breakdown`** is empty in Plex and is
  three keys wide, so its rows are only the keys they join.
- **Quality unit cost.** `Part_v_Part.Average_Value` is 0 on every part. A
  per-part unit cost is drawn once, near what the real descriptions imply
  ($600 on 890 units, $2,305.57 on one destruction).
- **Inventory standard costs** are per unit, like Plex's, and derived as
  follows:
  - Finished goods: 0.45 × the lowest real customer price.
  - Bright bottles: the real bottle-to-finished-good cost ratio.
  - Capsules, blends and labels: their real per-family costs.

## `proposed_sql/` — fixes the sandbox found, NOT deployed

A file here with the same name as one in `reports/sql/` replaces it **in the
sandbox only**. The build prints a `⚠ … using PROPOSED SQL (not deployed)`
line for each one, so nobody designs against it believing production already
behaves that way.

They exist because without them the tiles they feed cannot be designed at
all. Editing `reports/sql/` deploys to prod on the next `terraform apply`, and
that call is Emilio's.

**To retire one:** land the fix in `reports/sql/` (with its CHANGELOG entry
and `docs/reports/` update), then delete the override here. A stale override
would hide a regression.

**Empty right now.** The first three overrides (rep resolution, Deposit
Review, scrap flag) were landed in `reports/sql/` on 2026-09-24 and deleted
here, which is the lifecycle every override should follow. The folder stays so
the next fix found in the sandbox has somewhere to go first.

## Using it for Looker Studio

1. **Point every data source at `voxdatalake.ScorecardSandbox.<view>`**, never
   at a `raw_*` table.
2. **Build every tile from the view it will read in production.** The tile →
   view map is `TILES` in `scripts/board/board_data.py`.
3. **At go-live, change each source's dataset to `PlexProd`.** Anything built
   on a view that has a `proposed_sql/` override only works in prod once that
   fix is deployed.
4. **Never quote a sandbox figure as a business number.** It is shaped to
   behave like Vox's scorecard, not to be it.

## Changing it

- **A new tile.** Add it to `TILES` in `board_data.py`. The build picks up its
  view and base tables automatically. If the view is fed by tables no
  generator writes, it copies over with PlexTest's rows and nothing more.
- **A new family.** Add a module with `generate(sb)`, list it in
  `generators.FAMILIES` after anything it reads, and own disjoint tables.
- **Resetting while developing a module.**
  `build.copy_base_tables(sb, [its tables])` re-copies just those from the
  snapshot.

`scripts/scorecard_test_data.py`, the earlier per-tile injector, still exists
for quick PlexTest spot checks. It writes the "one part, one customer, $1.25"
rows this sandbox was built to replace, and the build strips them on copy.
