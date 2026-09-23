# Loading the scorecard with data before a demo

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

```bash
cd terraform && terraform plan -var-file=terraform.tfvars
```

If it shows `google_storage_bucket_object.*` changing, GCS is behind the repo.
`terraform apply` is the reliable deploy mechanism — it manages both
`reports/*.yaml` and `reports/test/*.yaml` as `source`-linked objects, so it
catches the prod/test pair that a manual `gcloud storage cp` will miss.

> `terraform apply` is blocked by this machine's local permission classifier —
> it has to be run by a human in their own terminal.

**Pending as of 2026-09-11:** `part_cycle_count_view.sql` (new),
`part_on_hand_inventory.yaml` and its test twin (two new extractions each).

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

## Faster iteration than a full apply

For a single SQL edit during a working session, `gcloud storage cp` is quicker
and `main()` re-creates the view on the next run:

```bash
gcloud storage cp reports/sql/<view>.sql gs://voxdatalake-report-configs/sql/
```

**This is iteration, not deployment.** It does not update the YAML pair, and it
leaves Terraform's state believing GCS matches the repo when it doesn't. Always
finish with a `terraform apply` so prod and test agree.

## Prod

Everything above is the `-test` jobs writing to `PlexTest`. The prod jobs email
the team on every run, so don't fire them to fix a demo — let the scheduled run
carry the change, then check with
`./scripts/scorecard_status.ps1 -Dataset PlexProd`.

## Proving a tile works: `scripts/scorecard_test_data.py`

A blank tile has two possible causes and they look identical from the
dashboard: **the view is wrong**, or **the Plex test tenant has nothing of
that kind**. This script settles it by putting rows underneath, so a tile that
stays blank with data present is one we have to fix.

```bash
python scripts/scorecard_test_data.py --status     # what is injected right now
python scripts/scorecard_test_data.py --inject     # all recipes, 14 days
python scripts/scorecard_test_data.py --inject --recipes production,shipping
python scripts/scorecard_test_data.py --delete     # remove every injected row
```

**The rows are not realistic and are not meant to be.** They are shaped to
satisfy the views (right columns, right types, right keys), so the figures will
not resemble Vox's business and must never be read as if they did. The question
being answered is "does anything arrive at all".

### How removal is guaranteed

Two independent mechanisms, because a cleanup that depends on a record of what
was written fails exactly when you need it:

1. **Every row is marked** - synthetic integer keys start at `990000000`,
   synthetic text keys start with `ZZTEST`. Nothing Plex generates comes near
   either, so `--delete` runs exact predicates and works even from a machine
   that has never run `--inject`.
2. A manifest table `_scorecard_test_data` records each batch, for `--status`.

`--delete` uses the predicates, not the manifest, so losing the manifest never
strands data. The tenant is also **wiped nightly at midnight UTC**, a third net.

**It refuses to run against `PlexProd`** - not a flag, not an override.

### What it proved on 2026-09-22

| Tile / view | Before | After |
|---|---|---|
| `shipping_daily_report` | 1 | **14** |
| `shipping_revenue_report` | 5 | **19** |
| `shipping_pending_revenue_report` | **0** | **4** |
| `production_monthly_by_workcenter_group_report` | 1 | **9** |
| `production_vs_goal_report` | 1 | **9** |
| `quality_fpy_by_area_month_report` | 1 | **9** |
| `inventory_avg_daily_usage_report` | **0** | **1** |
| `part_cycle_count_report` | **ERROR** | **1** (9 locations, 82.1% accuracy) |

That last row is the point of the exercise: `part_cycle_count_report` was not
empty, it was **unqueryable**. It cast an INT64 nanosecond date straight to
TIMESTAMP, which BigQuery rejects outright, so the view failed to parse. It had
been recorded as "0 rows, nothing counted yet" - and a status check that
reports row counts can never tell those two apart.

### Deliberately not covered

- **`inventory_valuation_total_report`** - needs `Part_v_Snapshot` plus two
  cost-breakdown tables including a history table, and a fabricated cost is the
  one number on this scorecard that would actively mislead rather than prove
  anything.
- **Quality** - already holds 22 real nonconformance records entered by Quality
  themselves. Nothing to prove.
