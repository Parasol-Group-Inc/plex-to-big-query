# Vox Scorecard | Goals Table

> **Status:** ✅ Created 2026-09-04 in `PlexTest` and `PlexProd`; joined by a second, app-fed table 2026-09-09 · **Category:** Reference data · **Fed by:** a Google Sheet via Apps Script — *not* the ETL

## What this is

The one maintained table behind every **"Goal"** and **"% to Goal"** figure on the Vox scorecard — revenue goals, sales goals by rep, and production goals by work centre group.

A negotiated target isn't a transaction Plex records, so no amount of ETL work produces it. Goals live in a spreadsheet people can actually edit, and an Apps Script pushes that sheet into BigQuery so the goal sits in the same dataset as the actuals and can be joined in SQL rather than blended in Looker Studio.

## Where it lives

```
voxdatalake.PlexTest.scorecard_goals
voxdatalake.PlexProd.scorecard_goals
```

**This table is not managed by Terraform and not created by the ETL.** It was created by hand in both datasets. The three views that read it — [`revenue_vs_goal_report`](revenue_vs_goal_report.md), [`sales_vs_goal_report`](sales_vs_goal_report.md), [`production_vs_goal_report`](production_vs_goal_report.md) — **fail to create if it's missing**, so don't drop it. Rebuild DDL is at the bottom of this page.

## Columns

| Column | Type | Meaning |
|---|---|---|
| `metric` | STRING | `revenue` \| `sales` \| `production` |
| `period_month` | DATE | First day of the goal month, e.g. `2026-09-01` |
| `scope` | STRING | Blank = company-wide. Otherwise a sales rep name or a work centre group. |
| `goal_value` | FLOAT64 | The target |
| `unit` | STRING | `USD` or `units` — a label for readers, nothing enforces it |
| `note` | STRING | Free text |
| `updated_by` | STRING | Who last edited the row in the sheet |
| `updated_at` | TIMESTAMP | Stamped by the Apps Script on each push |

## Why one long table instead of three

One row per (metric, month, scope) rather than a wide table with a column per metric. Revenue is company-wide, sales goals are per rep, and production goals are per work centre group — three different grains a wide table can't hold without NULL-padding or three separate tables to keep in sync. Long format also means **adding a new metric later is a new row, not a schema migration plus an Apps Script edit**.

## The one thing that will bite you

**`scope` is an exact string join.** The sheet must spell the value exactly as the matching report emits it:

- **Sales** → the `sales_rep` value from `sales_mtd_summary_report`, including the literal `(no rep assigned)` bucket that unassigned orders collapse into
- **Production** → the `workcenter_group` value from Plex. Confirmed live: **`Encapsulating`, not `Encapsulation`** — the Plex spelling differs from the scorecard tile name

A mismatch produces a NULL goal, not an error. All three views expose a flag (`goal_without_sales`, `goal_without_production`) so an unmatched goal row shows up rather than silently reading as 0%.

## There are now TWO goal tables

From 2026-09-09 a second table sits alongside this one:

```
voxdatalake.<dataset>.scorecard_goals       ← this page: the spreadsheet ETL
voxdatalake.<dataset>.scorecard_goals_app   ← the Apps Script WEB APP
```

Reports do not read either one directly any more — they read
[`v2_scorecard_goals_resolved`](v2_scorecard_goals_resolved.md), which
**prefers the app table and falls back to this one** for any goal not entered
in the form. Read that page for the precedence rules, the tombstone behaviour
and the sunset plan.

`scorecard_goals_app` shares this table's columns and adds one:

| Column | Type | Meaning |
|---|---|---|
| `is_deleted` | BOOL | `TRUE` retracts an override, so the goal falls back to the spreadsheet value rather than blanking the tile |

It is **append-only** — the newest row per `(metric, period_month, scope)`
wins — whereas this table is replaced wholesale on every push. Both are
hand-created and outside Terraform.

## How the push works

`deploy/goals_sheet_to_bigquery.gs`, run on a time-driven trigger from the spreadsheet.

- **WRITE_TRUNCATE** — the whole table is replaced on every push, so the sheet is the single source of truth and deleting a row there removes it here. An append-only load would accumulate duplicate goals for the same month and every "% to Goal" tile would quietly double.
- **Refuses to push an empty sheet** — that would truncate the table to nothing and blank every goal tile.
- **Schema is declared, not autodetected** — autodetect infers types from the first rows, so a month of round numbers can land `goal_value` as INTEGER and break the next push containing a decimal.
- **Bad rows are skipped and logged, not fatal** — one typo shouldn't stop every other goal reaching the scorecard.

## Current contents

`PlexTest` holds **68 real goal rows** — 8 reps x 7 months of sales goals loaded straight from Vox's existing `VoxScorecardsLive.sales_goals` table, plus 12 company-wide monthly figures lifted out of the hardcoded SQL in `vw_sales_mtd_vs_goal`. Both were loaded **by query, not retyped**, so there is no transcription risk. The 4 placeholder rows seeded 2026-09-04 were deleted once the real ones landed.

**Revenue and production goals are still empty, deliberately.** No real source exists for either — both live in Google Sheets nobody has exported. Entering the scorecard's rounded display values would have made every "% to Goal" subtly wrong forever with nothing recording where the numbers came from. Confirmed 2026-09-09 that revenue goals *do* exist and can be front-loaded, while production goals *"usually don't"* exist at all.

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
