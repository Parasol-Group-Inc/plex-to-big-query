# Goals | Resolved — the one goal per metric, month and scope

> **Status:** ✅ Deployed · **renamed from `scorecard_goals_resolved` 2026-09-22** when the duplicate "v2_" report views were retired — the three vs-goal reports now read this directly · **Category:** Reference data · **Runs:** rides the Sales Orders and Work Orders pipelines

## What this is

The migration seam between **two goal sources that both need to keep working**
while the scorecard moves off spreadsheets.

Goals used to arrive one way: a Google Sheet, pushed into
[`scorecard_goals`](scorecard_goals.md) by an Apps Script. From 2026-09-09
there is a second way — a **web app form** that writes straight to BigQuery,
because people kept breaking the sheet:

> *"I don't want to do it in a sheet because people tend to break the Google
> Sheets all the time."* — Jennilyn, 2026-09-09

This view picks between them, one goal at a time:

```
scorecard_goals_app   ← the web app (deploy/goals_web_app/)
scorecard_goals       ← the spreadsheet ETL (deploy/goals_sheet_to_bigquery.gs)
        ↓
scorecard_goals_resolved      ← app first, sheet as fallback
        ↓
revenue_vs_goal_report · sales_vs_goal_report · production_vs_goal_report
```

**A goal entered in the app wins. A goal not entered there falls through to
the spreadsheet.** So the scorecard never goes blank part-way through the
migration, and the two sources can run side by side for as long as it takes.

## Where it fits

- **The original three goal views are untouched** and still read the
  spreadsheet table, so Looker Studio can migrate **one tile at a time**
  rather than in a single cutover.
- The `v2_*` views are **generated copies** of the originals — same SQL, with
  the goal source swapped. `scripts/gen_v2_goal_views.py` produces them; edit
  the original and re-run it. They are not hand-maintained, deliberately: this
  repo has already been bitten by a pair of files that had to be edited
  together.
- **`goal_source` lives here, not on the report views.** Query this view to
  see whether a goal is coming from `app` or `sheet` — that keeps each `v2_`
  file a minimal diff from its original, which is what makes regenerating them
  safe.

## How it's built (high level)

The app table is **append-only**: every save inserts a row and the newest one
per `(metric, month, scope)` wins. Two people editing the same goal minutes
apart can't lose each other's write the way a read-modify-write would, and
every edit stays as history. The dedupe cost is trivial on a table of goals.

**Retracting a goal writes a tombstone rather than deleting the row.** A
tombstone means "the app has nothing to say about this key", so it falls back
to the spreadsheet value — which is the only sensible reading while both
sources are live. Retracting an override should restore the spreadsheet value,
not erase the tile.

- **Pipeline:** `reports/sales_orders.yaml` **and** `reports/work_orders.yaml`
  → `scorecard_goals_resolved`
- **SQL:** `reports/sql/scorecard_goals_resolved_view.sql`

It is listed in **both** pipelines on purpose: goal views live in both, and
each must be able to create its own dependency without waiting on the other's
run. The SQL is identical, so whichever runs second replaces an identical
view. It must stay listed **before** any `v2_*_vs_goal_report` in the same
config.

## Verified

Tested end to end on `PlexTest`, 2026-09-09, against the 68 real goal rows:

| Test | Result |
|---|---|
| Baseline | 68 rows, all `goal_source = 'sheet'` |
| App row written for a key the sheet already had | That key flipped to `app` with the new value; **still 68 rows** — the override displaced its twin rather than duplicating it |
| Tombstone written for the same key | Fell back to the sheet's **60,000** exactly; 0 rows from `app` |

Test rows were removed afterwards; the app table is empty until someone uses
the form.

## Flags and open questions

- **⚠ Both source tables are hand-created and outside Terraform, and this view
  fails to create if either is missing.** `scorecard_goals` predates this;
  `scorecard_goals_app` was created 2026-09-09 in `PlexTest` and `PlexProd`.
  Rebuild DDL for both is in [`scorecard_goals`](scorecard_goals.md).
- **Nothing enforces that the two sources agree.** That's the point — the app
  is an override layer. But it does mean a stale app row silently outranks a
  freshly corrected spreadsheet row for the same month. If a goal looks wrong
  after someone edits the sheet, check whether the app has an override for
  that exact key.
- **`scope` is still an exact string join.** The web app reads its dropdown
  options straight from the reports (`sales_mtd_summary_report`,
  `production_monthly_by_workcenter_group_report`) precisely so a typo can't
  create a goal that never matches — but a row loaded by any other route can
  still mismatch, and produces a NULL goal rather than an error.
- **Sunset plan, when the spreadsheet ETL goes:** delete the three original
  views, drop the `v2_` prefix, delete the `sheet` branch from this view (it
  becomes a thin read of the app table), and delete `scripts/gen_v2_goal_views.py`.
  No consumer of the `v2_` views has to change.

## More detail

`deploy/goals_web_app/README.md` covers the form itself, its setup, and the
Apps Script deployment trap (saving code does not update a live web app).
[`scorecard_goals`](scorecard_goals.md) documents the columns, which both
tables share.


## What changed on 2026-09-22

Until now there were **two of everything**: `revenue_vs_goal_report` read the
legacy goals table, and a generated `v2_revenue_vs_goal_report` read this
resolver — same for sales and production. That duality was the right call
while Looker Studio migrated one tile at a time, and it stopped being right
once nothing was left to migrate.

So: the three original reports now read this view, the three `v2_` copies are
gone, and this view lost its `v2_` prefix. **Nothing reads the goal tables
directly any more**, which means the "newest edit wins" rule lives in exactly
one place.

### The legacy leg is still here, on purpose

`scorecard_goals` still holds **68 real sales rep-month goals** — the only
copy. Its branch below stays until they are imported into the app's sheet by
running `importLegacyGoals()` from the manual-data Apps Script, which is a
one-click job somebody has to do. Then:

1. check `SELECT COUNT(*) FROM scorecard_goals_resolved WHERE goal_source = 'sheet'` reads **0**;
2. delete the `sheet` CTE and its UNION branch from the SQL;
3. drop `scorecard_goals`.

Also **disable the old Apps Script project**. Deleting
`deploy/goals_sheet_to_bigquery.gs` from the repo does not stop a deployed
trigger from still truncating that table on a schedule.
