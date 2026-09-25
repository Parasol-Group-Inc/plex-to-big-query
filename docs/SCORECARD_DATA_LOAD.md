# Loading the scorecard with data before a demo

Last reviewed: 2026-09-25

The goal: every Vox scorecard tile shows a real number, or we know exactly why
it doesn't and whose side that sits on. Written for the Sep-12 meeting, but the
sequence is the same any time.

**The honest framing up front:** most empty tiles are not a deployment problem.
They are empty because the Plex *test tenant* has no data of that kind yet.
Deploying harder does not fix those — entering data in Plex does. This runbook
separates the two so the meeting spends its time on the half that needs Vox.

---

## Step 0 — authenticate (only a human can do this)

```bash
gcloud auth login
```

The org security policy expires credentials periodically, and `bq`/`gcloud`
then fail with *"Reauthentication failed. cannot prompt during non-interactive
execution"* even though `gcloud auth list` still shows an active account. It
cannot be scripted around. **Nothing below works until this is done.**

## Step 1 — see where you actually are

```powershell
./scripts/scorecard_status.ps1 -Dataset PlexTest -Csv before.csv
```

One row per scorecard view, in three states that look identical on a dashboard
and mean completely different things:

| State | Meaning | Who fixes it |
|---|---|---|
| `n rows` | Real data | — |
| `0 rows` | View exists, upstream has nothing | Usually **Vox** (enter data in Plex) |
| `MISSING` | View was never created | **Us** — deploy, then re-run the job |

`MISSING` is the one to act on. A `gcloud run jobs execute ... --wait` that
exits 0 does **not** prove the view exists: extractions can all succeed while
view creation fails, and the job still reports PARTIAL and exits 0.

## Step 2 — deploy anything not yet in GCS

Everything the scorecard reads from GCS — both YAMLs of each pipeline and every
`reports/sql/*.sql` — is a `source`-linked Terraform object, so "is GCS behind
the repo?" and "deploy it" are the same command. Make sure the change is merged
to `main`, then from the primary folder:

```bash
cd C:/F/Parasol/plex-to-big-query && git pull
./scripts/deploy.sh
```

It plans, shows which `google_storage_bucket_object.*` would change (real
content changes separated from line-ending noise), and applies only after you
confirm the count. "Nothing to deploy." means GCS already matches `main`.
Terraform's deploy guard refuses from any other folder or branch.

## Step 3 — run the pipelines, in dependency order

Order matters exactly once, and it is not obvious: **`sales_orders` owns
`raw_Part_v_Part`**, which `part_on_hand_inventory`, `work_orders` and the
inventory pipelines all read rather than re-extracting. Run it first or those
views build against a stale part list.

```bash
# 1. sales_orders — owns the shared part tables and the goal resolver
gcloud run jobs execute plex-etl-sales-orders-test --region=us-central1 --wait

# 2. inventory and parts
gcloud run jobs execute plex-etl-part-on-hand-inventory-test --region=us-central1 --wait
gcloud run jobs execute plex-etl-inventory-activity-test     --region=us-central1 --wait
gcloud run jobs execute plex-etl-inventory-snapshot-test     --region=us-central1 --wait

# 3. production and quality
gcloud run jobs execute plex-etl-work-orders-test            --region=us-central1 --wait
gcloud run jobs execute plex-etl-quality-nonconformance-test --region=us-central1 --wait
```

Two things to check in the logs of each, because neither shows up in the exit
code:

- **`Report '<name>' loaded: N extraction(s)`** — compare N against
  `grep -c 'plex_view:' reports/test/<pipeline>.yaml`. A mismatch means the job
  picked up an older config than you think you deployed.
- **The view-creation section** — a failure here still exits 0.

## Step 4 — confirm, don't assume

```powershell
./scripts/scorecard_status.ps1 -Dataset PlexTest -Csv after.csv
```

Diff `before.csv` against `after.csv`. Every `MISSING` should now be `0 rows`
or better. Anything still `MISSING` is a real view-creation failure — read that
pipeline's job logs rather than re-running it.

---

## What will still be empty, and whose side it's on

This is the part worth walking through in the meeting, because no amount of
work on our side changes it.

### Needs data entered in Plex (Vox)

| Tile | Why it's empty | What makes it fire |
|---|---|---|
| **Out of Stock (33-parts)** | The calculation is proven — `33127-01VOXNU-1` is short 305,000 units — but both `33` parts have `Minimum_Inventory_Quantity = 0`, which the rule reads as "not assigned" | Any non-zero minimum on either part |
| **Production Daily / by Work Centre** | No job has logged real production on this tenant | Production logged against a job |
| **Quality tiles** (FPY, NC cost, disposition, TAT) | The quality tables are empty | Non-conformance and deviation records entered |
| **Inventory Value / Inventory Balance** | `Part_v_Snapshot` has no rows — Plex hasn't costed anything here | Plex costing run on the tenant |
| **Deviation $** | Needs both deviation rows *and* the costing above | Both of the above |

### Needs a decision, not data

`Rework $` (container-status version), the TAT standards, and the DPMO
opportunities figure — all on the sign-off board.

### Already has data, should show real numbers

Sales, revenue, shipping, WIP, pipeline, on-hand inventory, and all three goal
tiles — `scorecard_goals` carries 68 rows from the spreadsheet and
`scorecard_goals_app` carries the 12 loaded revenue goals, resolved by
`scorecard_goals_resolved`.

---

## Faster iteration than a deploy

**Don't copy SQL into the bucket.** There is one `sql/<view>.sql` object and
both the prod and the test jobs read it, so a copied file changes prod's next
run too — and a later deploy of `main` silently puts the old version back.
That is how a live fix was rolled back once already. Iterate without touching
GCS instead:

- run the view's SQL directly in BigQuery (replace `{gcp_project}` /
  `{dataset}` with `voxdatalake` / `PlexTest`), or
  `bq query --dry_run --use_legacy_sql=false "..."` to check it parses;
- prove a tile against realistic data in the **scorecard sandbox** (below).

Then land it the normal way: `dev-scorecard` → `main` → `./scripts/deploy.sh`,
and re-run the `-test` job. A YAML-only change may be tried first by copying
the **test** YAML to `gs://voxdatalake-report-configs/test/` and running the
`-test` job — see `docs/OPERATIONS.md` § "Edit an Existing Report".

## Prod

Everything above is the `-test` jobs writing to `PlexTest`. The prod jobs email
the team on every run, so don't fire them to fix a demo — let the scheduled run
carry the change, then check with
`./scripts/scorecard_status.ps1 -Dataset PlexProd`.

## Proving a tile works

Use the **scorecard sandbox**: `voxdatalake.ScorecardSandbox`, a full simulated
year under every tile that nothing overwrites — see
[`scripts/scorecard_sandbox/README.md`](../scripts/scorecard_sandbox/README.md).

```bash
python scripts/scorecard_sandbox/build.py          # full rebuild
python scripts/scorecard_sandbox/build.py --verify # rows + month span per view
```

### The earlier injector was retired on 2026-09-24

`scripts/scorecard_test_data.py` wrote marked rows straight into `PlexTest` to
tell a broken tile apart from an empty one. The sandbox does that job properly
— it clones real rows into a dataset nothing overwrites, rather than inventing
"one part, one customer, $1.25" rows in the dataset people actually look at —
so keeping both would have meant two ways to do one thing, with the weaker one
easier to reach for.

**It earned its keep before it went.** It is what exposed
`part_cycle_count_report` as *unqueryable rather than empty*: the view cast an
INT64 nanosecond date straight to TIMESTAMP, which BigQuery refuses, so it
failed to parse and every query against it errored. That had been recorded for
weeks as "0 rows, nothing counted yet" — a status check that reports row counts
can never tell those two apart. The fix is in `reports/sql/`, and the lesson
outlived the tool.

**Its one real flaw, recorded because the claim is still tempting:** it told you
its rows were "wiped nightly anyway". They were not. The nightly wipe clears the
*Plex tenant*, not BigQuery, and the ETL's zero-row guard — "0 rows → existing
table left untouched" — actively *preserves* injected rows when Plex returns
nothing. Two days after that run, 56 injected cycle-count rows and a fake safety
incident were still sitting in `PlexTest`, quietly feeding a tile. Anything that
writes test rows has to be deleted deliberately; "it expires on its own" is a
comforting thing to write and was simply false here.
