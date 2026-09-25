# Goals | Resolved — the one goal per metric, month and scope

> **Status:** ✅ Deployed · **renamed from `v2_scorecard_goals_resolved` 2026-09-22** when the duplicate "v2_" report views were retired — the three vs-goal reports now read this directly · **Category:** Reference data · **Runs:** rides the Sales Orders and Work Orders pipelines

## What this is

The single list of goals the scorecard uses: **one goal per metric, month and
scope** (a rep, a work centre group, or blank for company-wide). Every "% to
Goal" tile reads it, through [`revenue_vs_goal_report`](revenue_vs_goal_report.md),
[`sales_vs_goal_report`](sales_vs_goal_report.md) and
[`production_vs_goal_report`](production_vs_goal_report.md).

Goals are typed by people, not recorded by Plex. Today they are entered in the
**Manual Data app** (`deploy/manual_data_app/`), a web form that saves each
goal to a Google Sheet, which is pushed into BigQuery as `scorecard_goals_app`.
The form exists because people kept breaking the old goals spreadsheet:

> *"I don't want to do it in a sheet because people tend to break the Google
> Sheets all the time."* — Jennilyn, 2026-09-09

There is still one older source behind it: the legacy
[`scorecard_goals`](scorecard_goals.md) table, which is no longer updated.
This view picks between them, one goal at a time:

```
Manual Data app  ──►  Google Sheet  ──►  scorecard_goals_app   (current)
                                         scorecard_goals       (legacy, frozen)
                                                  ↓
                                   scorecard_goals_resolved    ← app first, legacy as fallback
                                                  ↓
          revenue_vs_goal_report · sales_vs_goal_report · production_vs_goal_report
```

**A goal entered in the app wins. A goal the app has nothing to say about
falls back to the legacy table.** So retiring the old table can never blank a
tile part-way through: until a goal exists in the app, the old value keeps
showing.

## Where it fits

- **Nothing else reads the goal tables directly.** All three vs-goal reports
  read this view, so the "newest edit wins" rule lives in exactly one place.
- **`goal_source` says where each goal came from:** `app` for the Manual Data
  app, `sheet` for the legacy table (named for the spreadsheet that used to
  feed it). Query this view, not the report, to check a goal's origin.
- **The legacy leg is on its way out.** The 68 legacy sales goals were
  imported into the app in `PlexTest` on 2026-09-24, so in test the app now
  holds them too. The fallback stays until `goal_source = 'sheet'` reads 0
  rows in every dataset this view runs in — see the 2026-09-22 section below
  for the steps.

## How it's built (high level)

The app table is **append-only**: every save adds a row and the newest one per
`(metric, month, scope)` wins. Two people editing the same goal minutes apart
can't lose each other's change, and every edit stays as history. The dedupe
cost is trivial on a table of goals.

**Retracting a goal in the app adds a "deleted" marker rather than removing
the row.** That means "the app has nothing to say about this key", so the goal
falls back to the legacy value if there is one. Retracting an override should
restore the previous value, not erase the tile. Once the legacy leg is gone, a
retraction will simply mean "no goal".

- **Pipeline:** `reports/sales_orders.yaml` **and** `reports/work_orders.yaml`
  → `scorecard_goals_resolved`
- **SQL:** `reports/sql/scorecard_goals_resolved_view.sql`

It is listed in **both** pipelines on purpose: the goal reports live in both,
and each must be able to create its own dependency without waiting on the
other's run. The SQL is identical, so whichever runs second replaces an
identical view. It must stay listed **before** the vs-goal reports in each
config.

## Verified

Tested end to end on `PlexTest`, 2026-09-09, against the 68 real legacy goal
rows:

| Test | Result |
|---|---|
| Baseline | 68 rows, all `goal_source = 'sheet'` |
| App row written for a key the legacy table already had | That key flipped to `app` with the new value; **still 68 rows** — the override displaced its twin rather than duplicating it |
| Retraction written for the same key | Fell back to the legacy **60,000** exactly; 0 rows from `app` |

Test rows were removed afterwards. On 2026-09-22, after the three reports were
switched to this view, `PlexTest` returned **80 goals — 12 from the app, 68
from the legacy table**, and `revenue_vs_goal_report` showed the app's revenue
goal where it previously showed none.

## Flags and open questions

- **⚠ Both source tables are hand-created and outside Terraform, and this view
  fails to create if either is missing** — which looks exactly like a broken
  view rather than a missing table. Rebuild DDL for both is in
  [`scorecard_goals`](scorecard_goals.md). Don't drop `scorecard_goals` until
  the legacy leg has been removed from the SQL.
- **An app goal always outranks the legacy one.** That is the point, but it
  means an old app entry beats anything in the legacy table for the same key.
  If a goal looks wrong, look at the app's value for that exact month and
  scope first.
- **`scope` is still an exact string match.** The app's dropdowns offer rep
  and work centre names straight from Plex-fed reports precisely so a typo
  can't create a goal that never matches — but a row loaded any other way can
  still mismatch, and produces a NULL goal rather than an error. Watch for
  Plex's `Encapsulating` versus the tile's "Encapsulation".
- **Production has no real goals yet** in either source, and the revenue goal
  is a copy of the company sales goal. Both are waiting on the business, not
  on this view. See [`docs/SCORECARD_SANDBOX_FINDINGS.md`](../SCORECARD_SANDBOX_FINDINGS.md)
  (Manual inputs).

## More detail

[`deploy/manual_data_app/README.md`](../../deploy/manual_data_app/README.md)
covers the form, how a save reaches BigQuery, and its setup.
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

**Update 2026-09-24:** `importLegacyGoals()` has been run in `PlexTest` — all 68 legacy goals are now in the app there. Before deleting the legacy branch, run step 1's check in **both** `PlexTest` and `PlexProd`.
