# Goals editor — Apps Script web app

A form that writes scorecard goals straight into BigQuery, so nobody edits a
spreadsheet and Jennilyn doesn't hand-edit the table. Agreed in the
2026-09-09 call (`meetings-reference/sep-9/`); modelled on her existing
sales-KPI web app.

> *"I don't want to do it in a sheet because people tend to break the Google
> Sheets all the time."* — Jennilyn, 2026-09-09

## Files

| File | What it is |
|---|---|
| `Code.gs` | Server side — BigQuery reads and writes, validation |
| `Index.html` | The form |

Both are pasted into an Apps Script project; this directory is the source of
truth so the code is reviewable and versioned, since Apps Script itself gives
you neither.

## What it writes, and why nothing breaks while both sources are live

```
scorecard_goals_app   ← this web app       (append-only)
scorecard_goals       ← spreadsheet ETL    (goals_sheet_to_bigquery.gs)
        ↓
v2_scorecard_goals_resolved   ← app first, sheet as fallback
        ↓
v2_revenue_vs_goal_report · v2_sales_vs_goal_report · v2_production_vs_goal_report
```

The app table is **append-only**: every save inserts a row, and the newest row
per `(metric, period_month, scope)` wins. Two people editing the same goal
minutes apart cannot lose each other's write, and every edit stays as history.

**A goal not entered here still comes from the spreadsheet**, so the scorecard
never goes blank mid-migration. **Retracting** a goal writes a tombstone
(`is_deleted = TRUE`) rather than deleting the row — which puts the
spreadsheet value back rather than blanking the tile.

The original `revenue_vs_goal_report` / `sales_vs_goal_report` /
`production_vs_goal_report` views are untouched and still read the spreadsheet
table, so Looker Studio can move one tile at a time. When the spreadsheet ETL
is sunset: delete the originals, drop the `v2_` prefix, and delete the sheet
branch from the resolver.

## Setup

1. Create an Apps Script project, paste in `Code.gs` and `Index.html`
   (the HTML file must be named `Index`).
2. **Services** (+) → **BigQuery API** → Add.
3. **Project Settings → Script Properties**:

   | Property | Value |
   |---|---|
   | `GCP_PROJECT` | `voxdatalake` |
   | `BQ_DATASET` | `PlexTest` → `PlexProd` at go-live |

   These live in properties rather than the code so the same script can point
   at test or production without an edit that needs redeploying.
4. Run `testReadsOnly()` from the editor first — it writes nothing and logs
   whether the reads work and how many goals are on file.
5. **Deploy → New deployment → Web app**, with:
   - Execute as: **Me** (so viewers need no BigQuery permissions)
   - Who has access: **Anyone within Parasol Group Inc**

## The deployment trap

**Saving the code does not update the live app.** You must
**Deploy → Manage deployments → edit → New version**. And the URL can change
when you do.

> *"If you make any changes to the code, even if you save it and run it, it
> won't update it unless you come in here and make a new version and deploy
> it. And sometimes that changes the URL."* — Jennilyn, same call

## Design notes worth knowing before changing it

- **Scope dropdowns are read from the reports, never typed.** `scope` is an
  exact string join: a goal whose scope doesn't match the report's spelling
  produces a NULL goal that reads as 0% forever, with no error. The live
  example is Plex spelling it `Encapsulating` while the scorecard tile says
  "Encapsulation". Reading the options from
  `sales_mtd_summary_report` / `production_monthly_by_workcenter_group_report`
  makes that class of mistake impossible.
- **The month must be the 1st.** Reports group by month; a goal dated
  mid-month would form its own bucket and never match. The form enforces it.
- **Company-wide is stored as a blank scope**, and displayed as
  `(company-wide)`, matching what the reports already emit.
- **Rep goals are summed against the company target as you type.** They are
  allowed to disagree — Jennilyn: *"even if their individual goals don't add
  up to this goal, we're just going to sum everything for the team."* The
  September gap ($5,040,000 team vs $4,690,000 across eight reps) comes from
  turnover. The form reports the gap; it does not block on it.
- **Writes go through `tabledata.insertAll`, not DML.** BigQuery limits
  concurrent DML on a table, which a form used by several people can hit.
  The cost is that a saved row takes a few seconds to appear in queries —
  which is why the form waits before re-reading. **If a save looks like it
  didn't land, reload rather than saving twice**; a second save just appends
  another row.
- **`skipInvalidRows: false`** on purpose: a schema drift should fail loudly
  rather than quietly write a goal that no report will match.
