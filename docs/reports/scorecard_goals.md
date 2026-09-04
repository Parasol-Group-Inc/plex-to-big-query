# Vox Scorecard | Goals Table

> **Status:** ✅ Table created 2026-09-04 in `PlexTest` and `PlexProd` · **Category:** Reference data · **Fed by:** a Google Sheet, via Apps Script — *not* the ETL

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

## How the push works

`deploy/goals_sheet_to_bigquery.gs`, run on a time-driven trigger from the spreadsheet.

- **WRITE_TRUNCATE** — the whole table is replaced on every push, so the sheet is the single source of truth and deleting a row there removes it here. An append-only load would accumulate duplicate goals for the same month and every "% to Goal" tile would quietly double.
- **Refuses to push an empty sheet** — that would truncate the table to nothing and blank every goal tile.
- **Schema is declared, not autodetected** — autodetect infers types from the first rows, so a month of round numbers can land `goal_value` as INTEGER and break the next push containing a decimal.
- **Bad rows are skipped and logged, not fatal** — one typo shouldn't stop every other goal reaching the scorecard.

## Current contents

`PlexTest` holds **4 placeholder rows** seeded 2026-09-04 so the joins could be verified end to end. Every one has `note = 'PLACEHOLDER — replace from the sheet'`. The first real Apps Script push replaces them. `PlexProd` is empty.

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
```
