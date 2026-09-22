# Manual Data — Apps Script web app

One form for every number that has to be **typed by a human** rather than
extracted from Plex. Replaces `deploy/goals_web_app/`, which covered goals
only and was never deployed.

## What it covers

| Dataset | Entered on | BigQuery table | Why it can't come from Plex |
|---|---|---|---|
| **Goals** | three tabs — Sales, Production, Revenue | `scorecard_goals_app` | Targets are negotiated, not recorded |
| **Safety incidents** | one tab | `safety_incidents` | Not in Plex at all; "days without an incident" counts from these |

The three goal tabs are a **presentation split only** (asked for by Jennilyn,
2026-09-21) — they all write the one `goals` dataset, one sheet tab and one
table. A dataset here is 1:1 with a sheet tab and a BigQuery table and pushes
are `WRITE_TRUNCATE`, so three real datasets would mean either three tables
(breaking every view that reads `scorecard_goals_app`) or three tabs racing to
truncate one table. Each tab pins `metric`, so the goal-type dropdown is gone —
the tab is the choice.

**Each form shows what is already saved, above the entry fields.** Pick a goal
type, month and scope and the current value appears; the incidents tab shows
the most recent incident. Jennilyn's reason, and it is the point: *"if they're
editing say a December goal, they're not really going to have visibility into
seeing what December's goal is in BigQuery to know that it's right or wrong
without asking me."* The lookup never blocks a save — if it fails, the panel
hides and the form still works.

### Removed, and why — read before adding either back

| Dataset | Removed | Why |
|---|---|---|
| **Turnaround standards** | 2026-09-22 | Jennilyn: *"I don't think we need it… they don't change those standards very much."* This reversed the 2026-09-11 plan to move them here with restricted edit access. ⚠ **They now have no home in BigQuery**, so `quality_turnaround_time_report` publishes actuals with nothing to measure them against — the comparison stays in the Monthly TAT Analysis sheet |
| **Part costs** | 2026-09-16 | Never a real requirement, just a fallback in case Plex's costing stayed empty. The real path is Plex fed by a NetSuite/Celigo sync — not a human typing numbers that would drift from both systems |

Adding another is a **registry entry in `Code.gs` plus `setupSheets()`** — no
new form code. If adding one requires editing `Index.html`, the registry is
missing a field type; that's the thing to fix.

## How it flows, and why the sheet is in the middle

```
web app  ──►  Google Sheet (one tab per dataset)  ──►  BigQuery table
              the durable log                          the mirror
```

Writing straight to BigQuery is the more obvious design, so the reasons for
the sheet are worth stating:

- **The sheet is the record.** Readable and fixable without BigQuery access,
  and it survives a table being dropped or the dataset being swapped from test
  to production. The BigQuery table is a mirror that `pushAll()` can rebuild.
- **Nobody types into the sheet.** The app is the only writer, and each tab
  says so in its header row. That keeps the "people break the sheets" problem
  away while still getting a human-readable log out of it.
- **The push is a load job**, not a streaming insert. A saved row is queryable
  **immediately** rather than sitting in a streaming buffer for a few seconds
  — which is what previously made a save look like it hadn't worked and
  invited someone to save twice.

Every tab is **append-only**: a save appends, an edit appends again, a
retraction appends a tombstone (`is_deleted = TRUE`). Two people editing the
same key minutes apart cannot lose each other's write. Consuming views take
the newest row per key.

`WRITE_TRUNCATE` is therefore not destructive — the full history goes across
on every push.

## Files

| File | What it is |
|---|---|
| `Code.gs` | The dataset registry, validation, sheet writes |
| `Push.gs` | Sheet → BigQuery load job, and the hourly safety-net trigger |
| `Index.html` | The form, generated from the registry |

This directory is the source of truth — Apps Script gives you no version
control, so code is reviewed here and pasted there.

## Setup

1. Create the spreadsheet that will hold the log. Note its id from the URL.
2. Create an Apps Script project; paste in `Code.gs`, `Push.gs` and
   `Index.html` (the HTML file must be named `Index`).
3. **Services (+) → BigQuery API → Add.**
4. **Project Settings → Script Properties:**

   | Property | Value | |
   |---|---|---|
   | `GCP_PROJECT` | `parasoldatalake` | the Apps Script project's own Cloud project — jobs **run and bill** here |
   | `BQ_DATA_PROJECT` | `voxdatalake` | where the **tables live**. Optional; defaults to `GCP_PROJECT` |
   | `BQ_DATASET` | `PlexTest` → `PlexProd` at go-live | |
   | `SHEET_ID` | the spreadsheet's id | the string between `/d/` and `/edit` |

   In properties rather than in the code so the same script points at test or
   production without an edit that needs redeploying. The environment shows as
   a badge in the form header, red for production.

   **The two project properties are deliberately separate.** The Apps Script
   project lives in `parasoldatalake` and the data lake is `voxdatalake`;
   collapsing them into one sends every query looking for
   `parasoldatalake.PlexTest.*`, which does not exist. The account that
   **deploys** the web app therefore needs `bigquery.jobs.create` on
   `parasoldatalake` and read/write on the `voxdatalake` datasets — everyone
   else needs nothing, because the app executes as the deployer.
5. Run **`setupSheets()`** once — creates a tab per dataset with the right
   headers. Safe to re-run; it never touches existing rows.
6. Run **`testReadsOnly()`** — writes nothing, reports what it can see.
7. Run **`installTriggers()`** once — the hourly `pushAll()` safety net.
8. **Deploy → New deployment → Web app:**
   - Execute as: **Me** (so people filling the form need no BigQuery access)
   - Who has access: **Anyone within Parasol Group Inc**

## The deployment trap

**Saving the code does not update the live app** — not even saving and running
it from the editor. You must **Deploy → Manage deployments → edit → New
version**, and the URL can change when you do.

## Design notes worth knowing before changing it

- **Dropdown values are read from the reports, never typed.** These are exact
  string joins: a value that doesn't match the report's spelling produces no
  error, just a NULL that reads as 0% forever. The live example is Plex
  spelling a work centre group `Encapsulating` where the scorecard tile says
  "Encapsulation". Part numbers come from Plex for the same reason — it's how
  `12335` was mistaken for `12335-01VOXNU-1` in `Product_Cost`.
- **An empty dropdown says so.** If the report behind a list can't be read,
  the field shows a warning rather than an empty list that looks like "there
  are no options".
- **A failed push does not fail the save.** The row is already in the sheet,
  which is the record; the form says the push lagged and the hourly trigger
  carries it across. The alternative — failing the save — loses what someone
  typed for a reason that has nothing to do with them.
- **The load job is waited on.** A load job is asynchronous, and without
  `waitForJob_` a failure would be invisible and the form would report success
  for a push that never happened.
- **`maxBadRecords: 0`** on purpose: schema drift should fail loudly rather
  than quietly write a table no report will match.
- **Every column is NULLABLE.** Required-ness is enforced at entry; a REQUIRED
  column would turn one bad historical row into a failed load for the whole
  table.
- **Goals: retracting restores the spreadsheet value.** `v2_scorecard_goals_resolved`
  reads a tombstone as "the app has nothing to say about this key", which
  falls back to `scorecard_goals` rather than blanking the tile — the only
  sensible reading while both goal sources are live.
- **Company-wide is a scope, not a separate form.** `(company-wide)` sits at
  the top of both the rep and work-centre-group lists and is stored as a
  **blank** scope, which is what the reports emit. Revenue is company-wide by
  definition and shows no scope field at all. Production had no way to enter a
  company-wide goal before this, so the production tile could only ever be
  compared against per-group targets that may not exist.
- **One entry can fill a run of months.** Goals are typically set once at the
  start of a year and changed occasionally, so `Apply to how many months?`
  writes each month as **its own row** — a later edit to one month leaves the
  rest alone. Capped at 24 so a typo cannot write years of rows.
- **Rep goals are summed against the company target as you type.** They are
  allowed to disagree: the team target and individual goals are maintained
  separately, and team performance sums actuals rather than goals. The
  September gap ($5,040,000 team vs $4,690,000 across eight reps) comes from
  turnover. The form reports the gap; it does not block on it.

## What still needs creating in BigQuery

`scorecard_goals_app` exists in `PlexTest` and `PlexProd`. The other three
tables are created by the first push (`CREATE_IF_NEEDED`), so no DDL is
needed — but **nothing reads them yet**. Views over `safety_incidents`,
`turnaround_standards` and `part_cost_manual` are a separate build.

For turnaround in particular, the standards are only half the tile: the
actuals come from `quality_turnaround_time_report` (`Closed_Date − Problem_Date`
per non-conformance), which is deployed. Joining the two is what produces the
"average work days vs Performance/Bonus standard by stock type" the
Weekly/Monthly TAT Analysis sheets show today — and the grain differs, so that
join is a real build rather than a view rename.
