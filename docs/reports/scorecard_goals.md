# Vox Scorecard | Goals Table

> **Status:** 🗄 **Legacy** — created 2026-09-04 in `PlexTest` and `PlexProd`; no longer pushed since 2026-09-22; kept only as the fallback behind [`scorecard_goals_resolved`](scorecard_goals_resolved.md) until retired · **Category:** Reference data · **Fed by:** nothing any more (goals are now entered in the Manual Data app) — *not* the ETL

## What this is

The **original** goals table behind the Vox scorecard's **"Goal"** and **"% to Goal"** figures — revenue goals, sales goals by rep, and production goals by work centre group. It is now the *legacy* half of a two-table setup: new goals are entered in the **Manual Data app** and land in `scorecard_goals_app`, and the reports read [`scorecard_goals_resolved`](scorecard_goals_resolved.md), which takes the app's goal first and only falls back to this table when the app has none.

A negotiated target isn't a transaction Plex records, so no amount of ETL work produces it. Goals have to be typed by people and stored in BigQuery beside the actuals, so they can be joined in SQL rather than blended in Looker Studio. This page still documents the column layout, which both goal tables share, and the rebuild DDL for both.

## Where it lives

```
voxdatalake.PlexTest.scorecard_goals
voxdatalake.PlexProd.scorecard_goals
```

**This table is not managed by Terraform and not created by the ETL.** It was created by hand in both datasets. [`scorecard_goals_resolved`](scorecard_goals_resolved.md) reads it, and the three reports behind the goal tiles — [`revenue_vs_goal_report`](revenue_vs_goal_report.md), [`sales_vs_goal_report`](sales_vs_goal_report.md), [`production_vs_goal_report`](production_vs_goal_report.md) — read that, so **all four fail to create if this table is missing**. Don't drop it until its branch has been removed from the resolver's SQL. Rebuild DDL is at the bottom of this page.

## Columns

| Column | Type | Meaning |
|---|---|---|
| `metric` | STRING | `revenue` \| `sales` \| `production` |
| `period_month` | DATE | First day of the goal month, e.g. `2026-09-01` |
| `scope` | STRING | Blank = company-wide. Otherwise a sales rep name or a work centre group. |
| `goal_value` | FLOAT64 | The target |
| `unit` | STRING | `USD` or `units` — a label for readers, nothing enforces it |
| `note` | STRING | Free text |
| `updated_by` | STRING | Who entered or last edited the goal |
| `updated_at` | TIMESTAMP | When it was saved (stamped by the Apps Script, not the person's own clock) |

## Why one long table instead of three

One row per (metric, month, scope) rather than a wide table with a column per metric. Revenue is company-wide, sales goals are per rep, and production goals are per work centre group — three different grains a wide table can't hold without NULL-padding or three separate tables to keep in sync. Long format also means **adding a new metric later is a new row, not a schema migration**.

## The one thing that will bite you

**`scope` is an exact string join.** A goal must spell the value exactly as the matching report emits it (the Manual Data app's dropdowns offer the report's own values for exactly this reason):

- **Sales** → the `sales_rep` value from `sales_mtd_summary_report`, including the literal `(no rep assigned)` bucket that unassigned orders collapse into
- **Production** → the `workcenter_group` value from Plex. Confirmed live: **`Encapsulating`, not `Encapsulation`** — the Plex spelling differs from the scorecard tile name

A mismatch produces a NULL goal, not an error. All three views expose a flag (`goal_without_sales`, `goal_without_production`) so an unmatched goal row shows up rather than silently reading as 0%.

## There are now TWO goal tables

From 2026-09-09 a second table sits alongside this one:

```
voxdatalake.<dataset>.scorecard_goals       ← this page: legacy, no longer pushed
voxdatalake.<dataset>.scorecard_goals_app   ← the Manual Data app (current)
```

Reports do not read either one directly any more — they read
[`scorecard_goals_resolved`](scorecard_goals_resolved.md), which
**prefers the app table and falls back to this one** for any goal not entered
in the form. Read that page for the precedence rules, the tombstone behaviour
and the steps to retire this table.

`scorecard_goals_app` shares this table's columns and adds one:

| Column | Type | Meaning |
|---|---|---|
| `is_deleted` | BOOL | `TRUE` retracts an app goal, so it falls back to this table's value (if any) rather than blanking the tile |

It is **append-only** — the newest row per `(metric, period_month, scope)`
wins. Both tables are hand-created and outside Terraform.

## How it was fed, and why it no longer is

Until 2026-09-22 an Apps Script (`deploy/goals_sheet_to_bigquery.gs`) copied a
Google Sheet into this table on a timer, replacing the whole table each time.
That script was **deleted from the repo on 2026-09-22**, when every goal moved
to one entry point, the Manual Data app. **Nothing writes to this table any
more.**

- **Its rows have been moved into the app.** The 68 real sales goals were
  imported into the app with `importLegacyGoals()` in `PlexTest` on
  2026-09-24, so the app now holds its own copy of each of them and the app's
  copy is the one the reports use.
- **It stays only as a fallback.** [`scorecard_goals_resolved`](scorecard_goals_resolved.md)
  still reads it for any goal the app has nothing to say about, so dropping
  it early can't blank a tile. It will be retired once the resolver shows no
  goal coming from it (`goal_source = 'sheet'` reads 0 rows) and its branch is
  removed from the resolver's SQL.
- **⚠ One loose end:** deleting the script from the repo does not switch off
  the copy deployed in Apps Script. If that old project is still enabled, its
  trigger can keep overwriting this table from the old sheet. It needs
  disabling by hand.

## Current contents

`PlexTest` holds **68 real goal rows** — 8 reps x 7 months of sales goals loaded straight from Vox's existing `VoxScorecardsLive.sales_goals` table, plus 12 company-wide monthly figures lifted out of the hardcoded SQL in `vw_sales_mtd_vs_goal`. Both were loaded **by query, not retyped**, so there is no transcription risk. The 4 placeholder rows seeded 2026-09-04 were deleted once the real ones landed. **All 68 were imported into the Manual Data app on 2026-09-24**, so in `PlexTest` the app's copy of each now takes precedence and these rows are only a fallback.

**Revenue goals were loaded 2026-09-09 — as overrides, and under a stated
assumption.** All 12 monthly figures now exist as `metric = 'revenue'` rows in
**`scorecard_goals_app`**, not here. Two things about that worth knowing:

- **Why the app table and not this one:** at the time this table was
  replaced wholesale on every spreadsheet push, so anything hand-loaded here
  would have disappeared the moment somebody saved the sheet. The app table is
  append-only, which is exactly what an override is for.
- **⚠ The assumption:** they are copied from the **company-wide sales goal**,
  because that is the only company-wide monthly target that exists anywhere in
  BigQuery (it was hardcoded as a 12-row `UNION ALL` inside
  `VoxScorecardsLive.vw_sales_mtd_vs_goal`, which measures it against
  `vw_sales.amount` by `date_approved` — i.e. **ordered**, not shipped).
  Revenue and Sales are deliberately different metrics in this pipeline, so
  **using the same target for both is a business assumption, not something the
  data proves.** Jennilyn said revenue goals "exist and we could frontload"
  them and no separate revenue target exists, so these are almost certainly
  what she meant. Every row carries a `note` saying exactly this, and
  retracting them is one tombstone away.

**Production goals are still empty, deliberately.** No real source exists for either — both live in Google Sheets nobody has exported. Entering the scorecard's rounded display values would have made every "% to Goal" subtly wrong forever with nothing recording where the numbers came from. Confirmed 2026-09-09 that revenue goals *do* exist and can be front-loaded, while production goals *"usually don't"* exist at all.

`PlexProd` is empty.

## Rebuild DDL

```sql
CREATE TABLE IF NOT EXISTS `voxdatalake.PlexTest.scorecard_goals` (
  metric       STRING   NOT NULL,
  period_month DATE     NOT NULL,
  scope        STRING,
  goal_value   FLOAT64  NOT NULL,
  unit         STRING,
  note         STRING,
  updated_by   STRING,
  updated_at   TIMESTAMP
);

-- The app-fed override table (2026-09-09). Same columns plus is_deleted.
CREATE TABLE IF NOT EXISTS `voxdatalake.PlexTest.scorecard_goals_app` (
  metric       STRING   NOT NULL,
  period_month DATE     NOT NULL,
  scope        STRING,
  goal_value   FLOAT64  NOT NULL,
  unit         STRING,
  note         STRING,
  updated_by   STRING,
  updated_at   TIMESTAMP,
  is_deleted   BOOL
);
```
