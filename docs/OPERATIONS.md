# Operations Guide

Last reviewed: 2026-09-25

Day-to-day operations: editing reports, adding new reports, configuring SendGrid, and managing environments.

> **Every change reaches production the same way:** commit on a `dev*` branch
> in its project folder → merge to `main` → `./scripts/deploy.sh` from the
> primary folder (`C:\F\Parasol\plex-to-big-query`). The full flow and every
> lock that enforces it: `CONTRIBUTING.md` § "Branches, folders and locks".
> Nothing in this guide is a way around that.

---

## How the Report System Works

Reports are defined by **YAML files** (plus the SQL files they point at) — not
hardcoded in the container image. The Cloud Run job reads them from Cloud
Storage at the start of every run, so a report change needs no image rebuild.
But the GCS copies are **Terraform-managed**: every file under `reports/`
(each pipeline's prod YAML, its test YAML, and every `reports/sql/*.sql`) is a
`google_storage_bucket_object` in `terraform/main.tf` with `source` pointing at
the repo file. `./scripts/deploy.sh` is what puts them in GCS.

```
gs://voxdatalake-report-configs/
├── reports/<pipeline>.yaml   ← PROD config, one per pipeline (13) → PlexProd
├── test/<pipeline>.yaml      ← TEST config, one per pipeline (13) → PlexTest
└── sql/<view>.sql            ← BigQuery view SQL — ONE copy, read by BOTH prod and test
```

14 pipelines, 29 Cloud Run jobs (prod + test, plus the Label Design push
job), 68 BigQuery views. Schedule for all of them: [EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md).

**Each YAML file contains:**
- `extractions[]` — list of Plex views to pull, with optional filters and destination table names
- `bq_view` — optional BigQuery VIEW definition (the SQL that JOINs raw tables into the report). Usually a single mapping (`{name, sql_file}`), but can also be a **list** of mappings when one extraction run should produce more than one view (e.g. a detail view and a separate aggregated rollup over the same raw tables — see `reports/inventory_snapshot.yaml`). Each view in the list is validated and created independently; one bad/failing view doesn't block the others.

The Cloud Run Job reads the YAML at startup on every run. The `REPORT_CONFIG_GCS_PATH` env var tells it which YAML to load.

> **The prod and test YAMLs are two hand-maintained files.** Any change to an
> `extractions:` or `bq_view:` list goes in both `reports/<pipeline>.yaml` and
> `reports/test/<pipeline>.yaml` (the pre-commit hook refuses a pair whose
> `plex_view:` counts differ). The SQL files are not paired — there is one.

---

## Edit an Existing Report

Every edit is a normal change: make it in the project's folder on its `dev*`
branch, commit it with its `CHANGELOG.md` entry, merge to `main`, deploy with
`./scripts/deploy.sh`. What follows is what to edit, and how to check it
safely **before** it goes through that flow.

> **Never `gcloud storage cp` into `reports/` or `sql/` in the bucket.** This
> guide used to recommend it as a "no-deployment" edit. That is how prod GCS
> drifted away from `main`, and how a later `terraform apply` of `main` then
> silently rolled a live fix back (the fix only ever existed in GCS). Copying
> into `test/` for a quick look is the only exception — see below.

### Change a filter on a Plex view

Edit the extraction in **both** YAMLs — find it and set the `filter` field:

```yaml
extractions:
  - plex_view: Sales_v_PO
    bq_table: raw_Sales_v_PO
    filter: "WHERE PO_Status_Key = 2073"   # ← add filter here
    date_col: ""
```

### Add a Plex view to an existing report

Add a new entry to the `extractions[]` list, in both YAMLs:

```yaml
  - plex_view: Sales_v_PO_Type        # ← Plex view name (always {DB}_v_{View})
    bq_table: raw_Sales_v_PO_Type     # ← BigQuery table name (choose anything)
    filter: ""                         # ← WHERE clause, or "" for all rows
    date_col: ""                       # ← timestamp column for incremental, or ""
    probe: [Update_Date, PO_Type_Key]  # ← optional: change-probe columns (MAX each; sum:Col for SUM)
    page_key: PO_Type_Key              # ← optional: pull in keyset pages by this integer column
    page_size: 25000                   # ← optional with page_key (default 25,000 rows per call)
```

`probe:` is filled for you by `python scripts/generate_probe_columns.py --write`.
Add `sum:` columns by hand, for rates, quantities and lead times only. Never use
`sum:` on a key: Plex's 32-bit SUM overflows. Use `page_key` only for a large
view (tens of thousands of rows or more). Paging and probing are explained in
`docs/TECHNICAL_REFERENCE.md` § "Change probe".

Check the pair still matches before committing:

```bash
grep -c 'plex_view:' reports/sales_orders.yaml reports/test/sales_orders.yaml
```

### Quick iteration on a YAML change — test path and `-test` job only

To see a YAML change run before merging, you may copy the **test** YAML into
the bucket's `test/` path and run the **test** job:

```bash
gcloud storage cp reports/test/sales_orders.yaml \
  gs://voxdatalake-report-configs/test/ --content-type=text/plain
gcloud run jobs execute plex-etl-sales-orders-test \
  --region=us-central1 --project=voxdatalake --wait
```

Then check the log line `Report 'sales_orders_test' loaded: N extraction(s)`
against the `grep -c` above, and query the view — a `--wait` exit code of 0
does not prove the view was created (CLAUDE.md). This is iteration, not a
deploy: the next `./scripts/deploy.sh` puts `test/` back to whatever `main`
says, which is the point. Land the change through the normal flow.

### Change the BigQuery JOIN view SQL

Edit `reports/sql/<view>.sql` and send it through the normal flow. **There is
only one copy of each SQL file in GCS (`sql/`), and prod and test both read
it** — so copying an edited SQL file into the bucket changes the *prod* job's
next run as well, not just test's. Don't. Iterate on SQL without touching GCS:

- **BigQuery dry run / console query** — paste the SQL with `{gcp_project}`
  and `{dataset}` replaced by `voxdatalake` and `PlexTest`, and run it (or
  `bq query --dry_run --use_legacy_sql=false "..."` to check it parses).
- **The scorecard sandbox** (`voxdatalake.ScorecardSandbox`, see
  [`scripts/scorecard_sandbox/README.md`](../scripts/scorecard_sandbox/README.md))
  for scorecard views that need realistic data behind them.

After `./scripts/deploy.sh` has put the new SQL in GCS, the next run of each
job that lists it does `CREATE OR REPLACE VIEW`. To see it at once, run the
`-test` job, then the prod job if you don't want to wait for its schedule.

> **Note on SQL placeholders:** The SQL file uses `{gcp_project}` and `{dataset}` which the container replaces at runtime with the `GCP_PROJECT` and `BQ_DATASET` env var values. Never hardcode `voxdatalake` or `PlexProd` in the SQL file — it must work for both prod and test.

> **Editing a view in the BigQuery console** lasts only until the next run
> recreates it from GCS. Fine for a look; never a fix.

---

## Add a Brand-New Report

This is the full end-to-end process. Use `work_orders` as a reference implementation — its files are the most up-to-date example of every pattern in use.

### Step 0 — Find the right Plex views

Before writing any code, verify the views exist and contain the columns you need.

1. Open **Plex SQL Developer** (or the ODBC query tool)
2. Browse the database tree — views are named `{Database}_v_{ViewName}` (e.g., `Part_v_Job`, `Sales_v_PO`)
3. Run `SELECT TOP 5 * FROM Part_v_Part AS pp` to confirm columns and data types — see the alias note below
4. Check [`catalog/plex_catalog_index.md`](../catalog/plex_catalog_index.md) for a cross-database index of known views

> **Corrected 2026-08-23 — this claim was backwards, and incomplete.** Plex SQL Developer requires every table referenced in a `SELECT` to be aliased — including a single-table query (`SELECT TOP 5 * FROM Part_v_Part AS pp`, not bare `FROM Part_v_Part`), not just joins. A query without an alias fails to run at all. Confirmed live by Emilio in the SQL Development Environment across two rounds of testing on 2026-08-23. This is the opposite of what the original note here said ("rejects trailing table aliases... use the full view name every time") — always alias every table.

> **No "Prod" database.** Work orders, jobs, and manufacturing data live in the **Part** database, not a "Prod" database. Check the catalog before assuming where a view lives.

### Step 1 — Create the YAML

```bash
cp reports/work_orders.yaml reports/purchasing_orders.yaml
cp reports/test/work_orders.yaml reports/test/purchasing_orders.yaml
```

Edit `reports/purchasing_orders.yaml`:

```yaml
report_name: purchasing_orders
category: Purchasing            # required for a correct email subject — see docs/TECHNICAL_REFERENCE.md
description: "Daily purchasing orders — Vox Nutrition (PlexProd dataset)"

extractions:
  - plex_view: Purchasing_v_PO
    bq_table: raw_Purchasing_v_PO
    filter: ""
    date_col: ""

  - plex_view: Purchasing_v_PO_Line
    bq_table: raw_Purchasing_v_PO_Line
    filter: ""
    date_col: ""

bq_view:
  name: purchasing_orders_report
  display_name: "Purchasing Orders"   # what recipients actually see — not the raw view name
  sql_file: gs://voxdatalake-report-configs/sql/purchasing_orders_view.sql
```

> **Don't skip `category`/`display_name`.** Without `category`, the subject falls back to the bare pipeline name (`[Plex ETL] - Purchasing Orders — DATE`) with no department in it; without `display_name`, the body's "Reports Produced" list shows raw view names. Pick `category` from [`reports-list/`](../reports-list/) (the department the report belongs to — Sales, Production, Quality, Supply Chain, ...) and `display_name` from the report's real name as your stakeholders know it, not the internal `bq_table`/`report_name` identifiers.

Edit `reports/test/purchasing_orders.yaml` — change only `report_name` to `purchasing_orders_test`:

```yaml
report_name: purchasing_orders_test
description: "Daily purchasing orders — TEST environment (PlexTest dataset)"
# ... same extractions and bq_view as prod ...
```

> **Shared tables:** If your report needs `raw_Part_v_Part` (already owned by `sales_orders`), do NOT add `Part_v_Part` to your extractions list. Reference it in your SQL as a shared table. Two pipelines running WRITE_TRUNCATE on the same raw table risk silently emptying it on a 0-row Plex response. See `reports/work_orders.yaml` for the comment pattern.

### Step 2 — Write the BigQuery SQL

```bash
cp reports/sql/work_orders_view.sql reports/sql/purchasing_orders_view.sql
# Edit to match your join logic
```

Key patterns to follow — see `work_orders_view.sql` for a full working example:

**Always use `{gcp_project}` and `{dataset}` placeholders — never hardcode:**
```sql
FROM `{gcp_project}.{dataset}.raw_Purchasing_v_PO` po
```

**Use `SAFE_CAST` for all numeric JOIN keys and aggregated columns:**

BigQuery autodetects schema from the row values when a table populates, so populated tables get proper types (INT64, FLOAT64). Since 2026-08-23 an empty table is typed from Plex's real ODBC column types (`cursor.description`) instead of all-STRING, but a populated column can still land as a different type than you assumed (e.g. a nullable int arriving as FLOAT64) and a JOIN on uncast columns then throws a type error.

```sql
-- Joining on a key that might be STRING in one table and INT64 in another:
LEFT JOIN `{gcp_project}.{dataset}.raw_Purchasing_v_Supplier` s
  ON SAFE_CAST(po.Supplier_Key AS INT64) = s.Supplier_Key

-- Aggregating numeric columns from an empty table (all STRING):
SUM(SAFE_CAST(line.Amount AS FLOAT64)) AS total_amount
```

`SAFE_CAST` is a no-op when the column is already the correct type — safe to apply defensively.

### Step 3 — Add the Terraform resources (GCS objects, jobs, schedulers)

Copy the **`sales_quotes`** blocks in `terraform/main.tf` — the most recent
complete single-view pipeline — and rename them. A pipeline is nine resources:

| Resource | Copy of | What to change |
|---|---|---|
| `google_storage_bucket_object` × 3 | `sales_quotes_config_prod`, `sales_quotes_config_test`, `sales_quotes_open_view_sql` | object `name` and `source` — one per YAML, plus **one per SQL file** the YAML lists (Terraform doesn't infer SQL files from `bq_view`; a missing one means that view's SQL never reaches GCS) |
| `google_cloud_run_v2_job` × 2 | `etl_sales_quotes`, `etl_sales_quotes_test` | `name` (`plex-etl-<pipeline>` / `plex-etl-<pipeline>-test`) and the `REPORT_CONFIG_GCS_PATH` value (`reports/…` vs `test/…`) |
| `google_cloud_scheduler_job` × 2 | `etl_sales_quotes_test`, `etl_sales_quotes_test_retry` | `name` (`plex-<pipeline>-sync-test[-retry]`), the job reference in `uri`, and the test `schedule` cron (Mountain time, `var.scheduler_time_zone`) — pick a free 10-minute slot from [EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md). The retry keeps `var.retry_scheduler_cron`. **Prod has no scheduler:** add the new prod job's rows to `PlexOps.etl_schedule` instead (see [ETL schedule](#etl-schedule-prod--plexopsetl_schedule)). |

Keep the `lifecycle { ignore_changes = [...image...] }` block on both jobs.

Also add both new job names to **`_ALL_JOBS` in `deploy/cloudbuild.yaml`** —
a job missing from that list never gets a new image from a Cloud Build deploy.

> **Note on `BQ_TABLE` and `PLEX_VIEW`:** these env vars are only used in the legacy single-view mode and have no effect when `REPORT_CONFIG_GCS_PATH` is set. You don't need to set them for new multi-report pipelines.

### Step 4 — Commit, merge, deploy

Commit the YAML pair, SQL, `main.tf` and `cloudbuild.yaml` changes together
with a `CHANGELOG.md` entry, a `docs/reports/<view>.md` doc, and a status-line
update in the `reports-list/`/`spreadsheets/` doc that tracks the report
(CLAUDE.md "Convention"). Push the `dev*` branch, merge to `main`, then from the
primary folder:

```bash
cd C:/F/Parasol/plex-to-big-query && git pull
./scripts/deploy.sh
```

> **Deploy Terraform-managed changes with `./scripts/deploy.sh`, from the
> primary folder on `main`.** It runs the preflight, plans to a file (the
> **deploy guard** inside Terraform refuses any branch but a clean, pushed
> `main` in the primary folder), separates real content changes from
> line-ending noise, flags destroys, asks you to confirm the change count,
> applies exactly that plan, and tags the commit `deploy/<UTC time>`.
> Background and every lock: `CONTRIBUTING.md`. Never a bare `terraform apply`.

A new job is created on whatever `image_url` in `terraform.tfvars` says.
Check that against a live job first — it can be several deploys stale:

```bash
gcloud run jobs describe plex-etl-sales-orders --region=us-central1 \
  --project=voxdatalake --format="value(spec.template.spec.template.spec.containers[0].image)"
```

### Step 5 — Deploy the image (only if Python code changed)

`main.py`/`email_utils.py`/`templates/` changes ship as an image, not through
Terraform. An image deploy has no guard inside it — run the preflight first,
every time, from the primary folder on an up-to-date `main`:

```bash
./scripts/deploy_preflight.sh
gcloud builds submit --config deploy/cloudbuild.yaml --project=voxdatalake \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .
```

> **Cloud Build safety:** the build's smoke test runs **`plex-etl-sales-orders-test`
> only** (writes to `PlexTest`). Production is never executed automatically —
> after the test run looks good, trigger prod yourself:
> `gcloud run jobs execute plex-etl-sales-orders --region=us-central1`

### Step 6 — Test and validate

```bash
# Trigger the test job
gcloud run jobs execute plex-etl-purchasing-orders-test \
  --region=us-central1 --project=voxdatalake --wait

# Then confirm the VIEW exists — exit code 0 does not prove it (CLAUDE.md)
bq query --use_legacy_sql=false --project_id=voxdatalake \
  "SELECT COUNT(*) FROM \`voxdatalake.PlexTest.purchasing_orders_report\`"
```

Check the log line `Report 'purchasing_orders_test' loaded: N extraction(s)`
against `grep -c 'plex_view:' reports/test/purchasing_orders.yaml`.

Check the email — subject will be `[Plex ETL] - {Category}: {Pipeline} — {date}`
(built in `email_utils.py` from the YAML's `category` and the pipeline name,
e.g. `[Plex ETL] - Sales: Quotes — 2026-09-25`). Each view's `display_name` is
listed in the body under "REPORTS PRODUCED". Status and PRODUCTION/TEST are
never in the subject — check the body for those.

---

## Environments: Prod vs Test

| Setting | Production | Test |
|---|---|---|
| Cloud Run jobs (14 pipelines) | `plex-etl-<pipeline>` — e.g. `plex-etl-sales-orders` (1 PM / 6 PM / 11 PM probe + 4 AM full) | `plex-etl-<pipeline>-test` — e.g. `plex-etl-sales-orders-test` (7:10 PM Mountain) |
| Schedulers | None per job (since 2026-10-19): the ETL dispatcher starts jobs from `PlexOps.etl_schedule` — see [ETL schedule](#etl-schedule-prod--plexopsetl_schedule). Exception: Label Design keeps `plex-label-design-sync` (every 15 min) and `plex-label-design-push-sync` (6:05 PM sweep; each run that extracts starts the push itself) | `plex-<pipeline>-sync-test` |
| Every job's time | [EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md) | |
| Failure retry | One follow-up probe 15 min later from the dispatcher; no `-retry` scheduler | 9:45 PM Mountain daily (`plex-<pipeline>-sync-test-retry`, 12 jobs) — see [Failure Retry](#failure-retry-945-pm-mountain) below |
| Plex ODBC Host | `vox.odbc.plex.com` ✅ | `vox.test.odbc.plex.com` ✅ |
| BigQuery Dataset | `PlexProd` | `PlexTest` |
| Report config (YAML) | `gs://voxdatalake-report-configs/reports/` | `gs://voxdatalake-report-configs/test/` |
| View SQL | `gs://voxdatalake-report-configs/sql/` — **shared** | same files |
| Status | ✅ Live | ✅ Active — develop and validate here first |

**Always test in the test environment first.** The test jobs write to `PlexTest` — safe to run repeatedly, no impact on production data.

### Trigger jobs manually

```bash
# Sales Orders
gcloud run jobs execute plex-etl-sales-orders-test --region=us-central1 --project=voxdatalake --wait
gcloud run jobs execute plex-etl-sales-orders --region=us-central1 --project=voxdatalake --wait

# Work Orders
gcloud run jobs execute plex-etl-work-orders-test --region=us-central1 --project=voxdatalake --wait
gcloud run jobs execute plex-etl-work-orders --region=us-central1 --project=voxdatalake --wait

# Any pipeline: plex-etl-<pipeline>[-test]; list them all with
gcloud run jobs list --region=us-central1 --project=voxdatalake
```

### Promote to production

Production changes only through `main` + `./scripts/deploy.sh` (top of this
guide). Once deployed, you can trigger the prod job instead of waiting for its
schedule — it reads `reports/<pipeline>.yaml` (not `test/`) and writes to
`PlexProd`. Prod runs email the whole recipient list, so don't fire them
repeatedly.

---

## Batch emails: the first job, then one digest (since 2026-10-21)

Jobs that run as a batch mail only at its two ends:

| Batch | First job (own report) | Last job (digest) |
|---|---|---|
| Prod 1 PM / 6 PM / 11 PM probe, 4 AM full run (`PlexOps.etl_schedule`, one batch per mode and hour) | earliest `run_time` in the hour | latest `run_time` in the hour |
| Test, nightly (Cloud Scheduler, 7:10 PM to 11:20 PM) | `plex-etl-sales-orders-test` | `plex-etl-part-lot-test` |

- **The first job** sends its usual report, with a line saying the rest of the
  batch reports in the digest.
- **The jobs in between** send nothing when they succeed or find no changes.
- **Any job that fails or ends partial** sends its own full report at once,
  wherever it sits in the batch.
- **The last job** sends its own report only if it failed or ended partial.
  It then waits up to 6 minutes (`DIGEST_WAIT_SECONDS`) for every job in the
  batch to log a result, and sends **one digest**: subject
  `[Plex ETL] - Digest — <date>`, a row per job with result, start time,
  duration, rows written and the error or changed tables. A job still running
  then shows as **NO RESULT YET**.
- **Follow-up probes, test retries (9:45 PM) and Label Design** are outside the
  batches and mail by their own rules, as before.

Who is first or last comes from `EMAIL_ROLE` (`first`/`middle`/`last`). For
prod the dispatcher computes it on every start (`batch_for` in
`deploy/etl_dispatcher/main.py`), so changing a time in `etl_schedule` moves
the roles with it. For test it is a fixed env var on each test job in
`terraform/main.tf`: **move a test cron and you must move `first`/`last` too.**

**The audit trail is `job_run_log`,** which now records per run: `batch_id`,
`batch_kind`, `email_role`, `report_name`, `started_at`, `duration_seconds`,
rows fetched and written, tables total and failed, the changed tables, the
error detail and the execution name. The digest is built from it.

```sql
SELECT job_name, status, run_mode, started_at, duration_seconds, rows_written, tables_changed, detail
FROM `voxdatalake.PlexProd.job_run_log`
WHERE batch_id = 'probe-1300-2026-10-22'
ORDER BY started_at
```

**Health checks in the digest (since 2026-10-22).** Under the table, an amber
box lists anything that needs a look, even when every job in the batch was OK:
- **Stale:** a job with no `success`/`skipped` run in 12 h (30 h in test;
  `STALE_AFTER_HOURS`).
- **Build drift:** a job whose last run (within 24 h) logged a different
  `build` than the digest's own. `job_run_log.build` is the image's git SHA,
  set by Cloud Build (`GIT_SHA`); `unknown` means a build from before 10-22.
- **Dispatcher:** `succeeded-unrecorded`, `lost`, `dispatch-failed` and
  `held-outage` rows in the last 24 h (prod only).

Known gaps: if the last job is skipped as busy or fails to start, no digest
goes out for that batch (each failure still emailed on its own). A batch's
member list is learned from `job_run_log` over the last 7 days, so on the first
day after deploy the digest cannot list a job that has not reported yet.

## Email Status Levels

Every emailed run carries one of these status badges:

| Badge | Color | Meaning |
|---|---|---|
| **SUCCESS** | Green | All extractions completed, all rows written |
| **PARTIAL** | Yellow | One or more extractions failed (ODBC error, BQ write error); other extractions completed successfully — check the Errors and Notes sections, and the failed rows in the extraction table |
| **FAILED** | Red | Job crashed before completing — ODBC connection refused, config load failed, BigQuery unreachable |
| **NO CHANGES** | Grey | A probe run found nothing changed in Plex since the last clean run, so nothing was extracted and BigQuery is unchanged. Short template, same subject. |

Since 2026-10-19:
- **Times are Mountain,** and the subject's date is the Mountain date, so an
  11 PM run threads with that day.
- **A "why it ran" line** sits under the stats: which tables changed, a config
  update, or the scheduled full run.
- **Errors come first.**
- **Per-table detail** sits in a compact table at the bottom.

For known error signatures (e.g. a specific ODBC error code), the Errors section adds a short 💡 hint in blue explaining what it means and whether it needs Plex Support or a config fix on our side — see `_KNOWN_ERROR_HINTS` in `email_utils.py` to add more as new error patterns get diagnosed.

> A PARTIAL run is not a silent failure — the email lists every failed extraction in the Errors section. Any rows that did succeed are still in BigQuery. The BigQuery VIEW still runs against whatever data is available. If the VIEW was refreshed while some extractions failed, the Events list includes an explicit warning that some source tables hold stale data.

---

## Change Probe

Every pipeline can start a run with a cheap question to Plex: has anything I
read changed since my last clean run? If not, it skips the extraction.

- **Label Design** has asked it every hour since 2026-10-01, every 15 minutes
  since 2026-10-22: an *explicit*
  probe on the release lines sitting in `Label Design` status.
- **Every nightly pipeline** got an *automatic* probe on 2026-10-19: one
  `COUNT(*)` plus `MAX(change date / key)` per table. Plex answers those on its
  side in well under a second per table.
- Prod moves to four runs a day (1 PM, 6 PM, 11 PM probe; 4 AM always full)
  in phase 2 of [PROBE_BUILD_PLAN.md](PROBE_BUILD_PLAN.md). Until then, nightly
  runs are full exactly as before.

**What happens on a probe run:**

1. The probe queries run. Their answers, together with a hash of the report's
   own YAML and SQL, make a fingerprint.
2. If it matches the last clean run's fingerprint, the job **stops there**. It
   writes a `skipped` row to `probe_log` and sends the short **"Probe ran —
   nothing to update"** email with the usual subject. Label Design stays
   silent, because it uses `EMAIL_MODE=on_error`.
3. Otherwise the run proceeds in full, and the email says which tables changed.

**A YAML or SQL deploy always runs in full.** Both are part of the
fingerprint, so a view-only deploy is never skipped. The old "trigger the job
by hand after a view-only deploy" step is gone (OPEN_ITEMS L10). **A code-only
(Cloud Build) change is not in the fingerprint.** It reaches a quiet
pipeline's tables at its next extracting run. To apply it now, start the job
by hand: a hand start of a nightly pipeline is always a full run.

**The fingerprint only advances after a `success` run.** A failed or partial
run leaves the stored value alone, so the next probe sees a difference and runs
again. The probe is the retry, so probe-driven jobs have no `-retry`
scheduler.

**The push has its own gate.** `plex-etl-label-design-push` counts, in
BigQuery, the view rows whose LCR the audit table has never recorded. If that
is 0 it returns before reading the Monday API key or paging the board, so a
quiet hour costs no Monday API calls at all. It can over-count (a hand-typed
board item has no audit row) but never under-count, so the board scan stays the
final authority.

**The push board is "Plex Import Test" (18437236736) since 2026-10-27.** The
team moves items from it to "Design & QA". A move carries a status value across
by the label's colour (not its name), and the old "Plex Import" board's colours
did not match Design & QA's. Before creating items, the push gives every status
label it writes the colour that label has on Design & QA (`MOVE_TO_BOARD_ID`),
adding a missing label to both boards (`label_design_service/labels.py`). Its
log shows each change as `Label colours: ...`; a label it cannot make safe is a
`WARNING` and a non-zero exit. A label someone adds by hand should get the same
colour on both boards.

**The push emails its problems (2026-10-27).** Subject `[Plex ETL] - Sales:
Label Design push — <date>`, to the ETL's recipients: nothing created (a label
check failed), a field that will arrive blank (Design & QA refused a label),
items failed or partial, the alarm, a crash, and labels it added to Design &
QA. Once a day per problem; each email is recorded as `outcome = 'alert'` rows:

```sql
SELECT pushed_at, detail FROM `voxdatalake.PlexProd.label_design_push_log`
WHERE outcome = 'alert' ORDER BY pushed_at DESC LIMIT 20;
``` From 2026-10-22 to 10-27 a repair job
(`plex-etl-label-design-repair`) refilled those columns; it is retired, and its
`outcome = 'repaired'` rows stay in `label_design_push_log`. The push dedupes
against the push log for every board, so nothing pushed to the old board is
pushed again. To check a move kept its values, compare the item on Design & QA
with its push log row:

```sql
SELECT pushed_at, monday_item_id, customer_part_no, column_values
FROM `voxdatalake.PlexProd.label_design_push_log`
WHERE board_id = '18437236736' AND outcome IN ('created', 'partial')
ORDER BY pushed_at DESC LIMIT 20;
```

### Checking it is actually working

The probe **fails open**: anything that stops it being evaluated runs the full
extraction and logs `inconclusive`. That is the right default, but a
permanently broken probe looks like success while doing the full work every
time. Two queries worth running now and then:

```sql
-- Should be empty. Rows here mean the probe is not gating anything.
SELECT report_name, probed_at, detail FROM `voxdatalake.PlexProd.probe_log`
WHERE outcome = 'inconclusive' ORDER BY probed_at DESC LIMIT 20;

-- Today, per pipeline: how often it skipped vs ran.
SELECT report_name, outcome, COUNT(*) AS n
FROM `voxdatalake.PlexProd.probe_log`
WHERE DATE(probed_at, 'America/Denver') = CURRENT_DATE('America/Denver')
GROUP BY 1, 2 ORDER BY 1, 2;
```

**Adding the probe to a new pipeline:** put `probe_mode: auto` above
`extractions:`, then run `python scripts/generate_probe_columns.py --write`.
It fills `probe: [...]` for any extraction that lacks one, in both the prod
and test YAML. Review the dry run first.

---

## ETL schedule (prod) — `PlexOps.etl_schedule`

Since **stage B of probe phase 2 (2026-10-19)**, prod ETL run times live in a
**table**, not in Cloud Scheduler. There are no per-job prod schedulers and no
prod retry. Test jobs keep their nightly scheduler and the 9:45 PM retry
below. The dispatcher (`etl-dispatcher`, called every 5 minutes)
starts whatever is due. Test jobs keep their own nightly schedulers.

**See the schedule:**
```sql
SELECT job_name, run_time, mode, enabled FROM `voxdatalake.PlexOps.etl_schedule`
ORDER BY run_time, job_name;
```

**Change a time, or pause a job.** No deploy needed; it takes effect within
5 minutes.
```sql
UPDATE `voxdatalake.PlexOps.etl_schedule`
SET run_time = '13:30', updated_by = 'emilio', updated_at = CURRENT_TIMESTAMP()
WHERE job_name = 'plex-etl-sales-orders' AND run_time = '13:00';

UPDATE `voxdatalake.PlexOps.etl_schedule`
SET enabled = FALSE, updated_by = 'emilio', updated_at = CURRENT_TIMESTAMP()
WHERE job_name = 'plex-etl-sales-orders';
```

- **`mode`:** `probe` skips when nothing changed in Plex; `full` always
  extracts. Keep one `full` time a day per job: it catches edits the probe
  can't see.
- **`run_time`:** America/Denver wall clock (`HH:MM`).
- **A typo is reported, not ignored.** A bad `run_time` or `mode` appears in
  the dispatcher's `errors` (Cloud Logging, `etl-dispatcher`).

**What happened today:**
```sql
SELECT job_name, mode, reason, scheduled_for, dispatched_at, outcome, finished_at, detail
FROM `voxdatalake.PlexOps.etl_dispatch_log`
WHERE DATE(dispatched_at, 'America/Denver') = CURRENT_DATE('America/Denver')
ORDER BY dispatched_at DESC;
```

**Outcome values:**
- **`success` / `partial` / `failed` / `skipped`:** written by the job.
  `skipped` means the probe saw no change.
- **`skipped-busy`:** the previous run of that job was still going.
- **`lost`:** no outcome after 2 h.
- **`dispatch-failed`:** Cloud Run refused the start.
- **`succeeded-unrecorded`:** Cloud Run says it succeeded, but the job wrote
  no outcome.
- **`held-outage`:** not started, because Plex was refusing connections (see
  below). Its job gets one recovery run once Plex is back.

**`reason` values:** `schedule`, `follow-up`, `canary`, `recovery`.

**Retries.** A `failed` / `partial` / `lost` run gets one follow-up probe 15
minutes later (`reason = 'follow-up'`), unless the job has run again since.
There's no other retry.

### Plex outages: breaker, canary, recovery (since 2026-10-22)

When Plex stops answering ODBC, retrying every job is useless and mails a
failure per job. The dispatcher stops instead.

1. **Opens:** the two newest finished runs that say anything about Plex both
   failed with `ODBC connection failed` (`OUTAGE_THRESHOLD`). A failure of
   another kind (bad SQL, a view) does not count either way.
2. **While open:** due slots are logged `held-outage` and not started; no
   follow-ups. One **canary** probe runs at a time, 10 minutes apart
   (`CANARY_INTERVAL_MINUTES`), preferring the fastest jobs (`CANARY_JOBS`).
   The first canary's failure emails once, saying Plex is down; the rest are
   silent. The tick logs at `WARNING` with `"outage": {...}`.
3. **Closes:** the first run that reaches Plex (a canary that succeeds).
4. **Recovery:** each job with a `held-outage` slot in the last 24 h gets ONE
   run (`reason = 'recovery'`, `followup_of` = the held slot), full if any
   held slot was full, 4 per tick, as one batch with a digest. A later run of
   the job covers it: a full run covers anything, a probe covers a probe.

**Jobs the dispatcher does not start** (since 2026-10-27). `plex-etl-label-design`
runs every 15 minutes from its own scheduler, so it reads the breaker itself
(`OUTAGE_BREAKER_TABLE` in `main.py`, same rule as above). While it is open the
run ends `skipped` in `job_run_log` with `detail = "Held — Plex outage breaker
open since ..."`, without calling Plex or emailing. It gets no recovery run:
its next run after a canary connects catches up. If the dispatch log can't be
read, the run connects anyway.

**Is Plex down right now?**
```sql
SELECT job_name, reason, outcome, dispatched_at, detail
FROM `voxdatalake.PlexOps.etl_dispatch_log`
WHERE reason IN ('canary', 'recovery') OR outcome = 'held-outage'
ORDER BY dispatched_at DESC LIMIT 30;
```

**Connect deadline (the job side).** Each Plex connect gets 60 s wall-clock
(`CONNECT_DEADLINE_SECONDS`), 3 attempts (`CONNECT_ATTEMPTS`), backoff 20 s
then 40 s (`CONNECT_BACKOFF_SECONDS`). A login refusal (`28xxx`) fails at
once. The error reads `ODBC connection failed: 3 attempt(s); last: ...`;
keep that prefix, the breaker matches it.

**Dry run** (from a terminal with gcloud):
```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://us-central1-voxdatalake.cloudfunctions.net/etl-dispatcher?dry_run=1"
```

---

## Failure Retry (9:45 PM Mountain) — TEST jobs only since 2026-10-19

> **Prod no longer has this.** Since probe phase 2 stage B, prod jobs have no
> `-retry` scheduler and `max_retries = 0`. A failed prod run gets one
> follow-up probe 15 minutes later from the dispatcher (§ ETL schedule above).
> What follows describes the **test** jobs, which keep it.

The 12 test jobs that have a retry carry a second Cloud Scheduler trigger that
fires daily at **9:45 PM `America/Denver`** (handles the MST/MDT switch
automatically — no manual adjustment needed). The naming is uniform —
`plex-<pipeline>-sync-test-retry` retries `plex-etl-<pipeline>-test`. (The prod
`plex-<pipeline>-sync-retry` schedulers were removed 2026-10-19.)

| Retry scheduler | Retries |
|---|---|
| `plex-sales-orders-sync-test-retry` | `plex-etl-sales-orders-test` (test) |
| `plex-work-orders-sync-test-retry` | `plex-etl-work-orders-test` (test) |
| … one per test pipeline except Label Design and Part Routing | |

**Label Design has no retry trigger** (both were removed 2026-10-01). It runs
every 15 minutes behind a change probe, and a failed or partial run leaves the
stored fingerprint where it was, so the next probe sees a difference and runs
again — the probe is the retry. The same holds for the Monday push it starts
(`POST_RUN_JOB`, 2026-10-22): a push that cannot be started turns the run
partial, so the next probe re-runs and starts it again.

**How it decides whether to actually do anything:** the retry trigger
re-invokes the *same* Cloud Run Job with `RUN_MODE=retry` (a per-execution
env override — the job definition itself is untouched). At startup, the job
checks a `job_run_log` BigQuery table (in the same dataset it already
writes to) for the most recent **scheduled**-mode run logged today:

- **FAILED** → proceeds with a full real run, same as any other execution
- **no scheduled run logged today** → also proceeds with a full run (see the
  caution below)
- **SUCCESS or PARTIAL** → already covered for today; the job exits cleanly
  without doing any real work and **without sending an email** (a silent
  no-op, to avoid inbox noise from a trigger that had nothing to do)

Only a genuine **FAILED** run triggers a retry — **PARTIAL** does not,
since that's a different severity tier (some data got through) and isn't
treated as "the run needs to happen again."

> **Caution — the retry may not be running at all. Settled from the code,
> 2026-10-01.** Two separate things were suspected here; the code answers both.
>
> **1. The UTC edge is real.** `run_date` and the check both use UTC, and 9:45
> PM Mountain is already the next UTC day. A job scheduled *after* the retry
> (sales quotes, sales returns, quality supplier returns, and
> `plex-etl-purchasing-pending-requisitions-test` at 9:50 PM) has no
> "scheduled run today" when its retry fires. `main.py` then logs *"today's
> status: not logged — proceeding with a full run"* and does the full run,
> email included. So the code path the old caution described is genuine.
>
> **2. But it cannot be happening, because no retry is reaching the
> container.** Every retry invocation writes exactly one `job_run_log` row with
> `run_mode='retry'` — there is no path that returns without logging. A
> no-op logs `status='skipped'`; a real run logs `success`/`partial`/`failed`.
> `job_run_log` has **zero** `run_mode='retry'` rows since 2026-07-21, across
> 23 failed and 39 partial runs (OPEN_ITEMS D2). Those two facts can only both
> be true if the retry schedulers are not invoking the jobs, or the container
> is dying before `run_and_report()` is entered.
>
> **So the thing to check is not `job_run_log` — it is Cloud Scheduler.** The
> retry's own execution history says whether it fires and what the target
> returns:
>
> ```bash
> gcloud scheduler jobs describe plex-sales-orders-sync-test-retry --location=us-central1 --project=voxdatalake
> ```
>
> Until that is answered, **do not rely on the retry for any pipeline.** The
> nightly cascade currently has no working automatic retry — a failed run waits
> for a human. (Label Design is the exception: it has no retry trigger by
> design, because its hourly probe re-runs a failed cycle on its own.)

**Checking what happened:**
```sql
SELECT job_name, run_date, status, run_mode, logged_at
FROM `voxdatalake.PlexProd.job_run_log`   -- or PlexTest for the test jobs
ORDER BY logged_at DESC
LIMIT 20
```
`job_name` is the Cloud Run job name (`plex-etl-sales-orders`, `plex-etl-sales-orders-test`, etc. —
from the `CLOUD_RUN_JOB` env var Cloud Run sets automatically). `run_mode`
is `scheduled` or `retry`; `status` is `success`/`partial`/`failed`, or
`skipped` for a retry that no-op'd.

**Pausing a retry temporarily** (e.g. during planned maintenance), without
touching Terraform:
```bash
gcloud scheduler jobs pause plex-sales-orders-sync-test-retry --location=us-central1 --project=voxdatalake
gcloud scheduler jobs resume plex-sales-orders-sync-test-retry --location=us-central1 --project=voxdatalake
```

**Changing the retry time/timezone:** edit `retry_scheduler_cron` /
`retry_time_zone` in `terraform.tfvars` (live values: `"45 21 * * *"` /
`"America/Denver"`; the `variables.tf` defaults are `"0 6 * * *"` /
`"America/Denver"`) — applies to all 24 retry schedulers at once — back up
`terraform.tfvars` (its header has the command), then `./scripts/deploy.sh`
from the primary folder. `terraform.tfvars` exists only there.

---

## Backups

Code is on GitHub (every branch pushed). Terraform state lives in `gs://voxdatalake-terraform-state`, which has object versioning on since 2026-10-27 (not Terraform-managed). Tables that exist only in BigQuery, with no Plex source and no copy in git, are snapshotted into `voxdatalake.Backups` as `<Dataset>__<table>_<YYYYMMDD>`, expiring after 90 days. BigQuery time travel alone reaches back only 7 days.

- **List them:** `bq ls --project_id=voxdatalake Backups`
- **Restore one (to a new table, then compare before swapping):** `bq cp -f voxdatalake:Backups.PlexOps__etl_schedule_20261027 voxdatalake:PlexOps.etl_schedule_restored`
- **Take a fresh one:** `bq cp --snapshot --expiration=7776000 voxdatalake:PlexProd.safety_incidents voxdatalake:Backups.PlexProd__safety_incidents_<YYYYMMDD>`
- **Not covered:** the manual-data app's Google Sheet is the record for its tables (the BigQuery tables mirror it), and the three Apps Script projects hold their own deployed copies.
- **Weekly:** scheduled query `backup_snapshots_weekly` takes a fresh snapshot of every covered table each Monday 06:00 UTC. The table list is `terraform/backup_snapshots.sql`; add a table there to cover it.

## Data Safety Guards

These are enforced by `main.py` (added in the 2026-07-14 code review — see [archive/CODE_REVIEW_2026-07-14.md](archive/CODE_REVIEW_2026-07-14.md)):

| Guard | Behavior |
|---|---|
| **0-row protection** | If Plex returns 0 rows for a view (timeout, maintenance window, over-tight filter), the existing BigQuery table is **left untouched** — yesterday's data and schema are preserved, and a warning is logged. The table is only created (empty) if it doesn't exist yet. |
| **YAML validation** | `plex_view`, `bq_table`, and `date_col` must be plain identifiers (letters, digits, underscores). `filter` may not contain `;`, `--`, or `/*`. An invalid entry is skipped and reported as a PARTIAL error — it never reaches the ODBC connection, and it doesn't crash the other extractions. |
| **Config sanity check** | An empty or malformed YAML file fails fast with a clear error message instead of a cryptic traceback. |
| **No automatic prod runs** | Cloud Build's smoke test only ever executes the test job. |

---

## Full vs Incremental Sync

**Every extraction today is a full refresh** — the entire table is replaced each run (`WRITE_TRUNCATE`). Incremental sync (append only new/changed rows) is **not implemented yet**.

What `date_col` actually does today:

```yaml
  - plex_view: Sales_v_PO_Change
    bq_table: raw_Sales_v_PO_Change
    filter: ""
    date_col: Change_Date    # ← ORDER BY on the Plex query + sync watermark
```

1. Adds `ORDER BY Change_Date ASC` to the Plex query
2. Records the column's max value as `max_modified_at` in the `sync_metadata` table — so if incremental sync is built later, the watermark history is already accurate

If incremental sync is implemented in the future, use BigQuery **query parameters** (not string interpolation) for the watermark comparison — see finding 9 in [archive/CODE_REVIEW_2026-07-14.md](archive/CODE_REVIEW_2026-07-14.md).

---

## YAML Schema Reference

```yaml
report_name: string           # required — identifier for logs and email reports
description: string           # optional — human-readable description

probe:                        # optional — hourly pipelines only; skips the whole
                              # run when nothing changed. See "Change Probe" above.
  queries:
    - plex_view: string       # required — Plex ODBC view name
      columns: [string]       # required — columns to fingerprint
      filter: string          # optional — WHERE clause; alias every table as t
      bind: string            # optional — expose this query's single column to a
                              # later query's {name} placeholder (integers only)

extractions:                  # required — list of Plex views to extract
  - plex_view: string         # required — Plex ODBC view name ({DB}_v_{View})
    bq_table: string          # required — destination BigQuery table name
    filter: string            # optional — SQL WHERE clause, e.g. "WHERE Active = 1"
    date_col: string          # optional — ORDER BY + sync watermark (identifier chars only)

bq_view:                      # optional — BigQuery VIEW(s) to create after extraction
  name: string                # VIEW name in BigQuery
  sql_file: string            # gs:// URI to a .sql file (uses {gcp_project}/{dataset})
  sql: string                 # inline SQL alternative (same placeholders)

# bq_view may also be a LIST of the above mappings, to create more than one
# view from a single extraction run (e.g. a detail view + an aggregated
# rollup over the same raw tables):
#
# bq_view:
#   - name: detail_report
#     sql_file: gs://.../detail_view.sql
#   - name: summary_report
#     sql_file: gs://.../summary_view.sql
#
# Each entry is validated and created independently — a bad name or missing
# sql/sql_file on one entry doesn't block the others. See
# reports/inventory_snapshot.yaml for a real example.
```

---

## SendGrid Email Reports

After every run the pipeline can email an HTML summary with status, row counts per table, and any errors.

### Setup

**1. Get a SendGrid API key**
- Log in at [app.sendgrid.com](https://app.sendgrid.com) → Settings → API Keys → Create
- Name it `plex-etl-sales-orders`, restrict to **Mail Send** only

**2. Verify your sender email**
- Settings → Sender Authentication → Single Sender Verification
- Must match `report_from_email` in `terraform.tfvars`

**3. Store the key in Secret Manager**

```bash
echo -n 'SG.your-key-here' | \
  gcloud secrets versions add sendgrid-api-key \
  --data-file=- --project=voxdatalake
```

**4. Enable in `terraform/terraform.tfvars`**

```hcl
sendgrid_enabled  = "true"
report_from_email = "marketing@parasolgroupinc.com"
report_to_emails  = "emilio.dominguez@parasolgroupinc.com,jennilyn.tockstein@parasolgroupinc.com"
company_name      = "Vox Nutrition"
```

Then back up `terraform.tfvars` (command in its header) and run `./scripts/deploy.sh` from the primary folder.

**5. Test**

```bash
gcloud run jobs execute plex-etl-sales-orders-test \
  --region=us-central1 --project=voxdatalake --wait
# Check inbox within 1 minute
```

If no email arrives:
- Check logs for `SendGrid report sent with status 202`
- Verify sender address is confirmed in SendGrid
- Check spam folder
- Confirm the API key: `gcloud secrets versions access latest --secret=sendgrid-api-key --project=voxdatalake`

---

## Checklist for Each New Table or Report

- [ ] Identify the Plex view name (`{Database}_v_{ViewName}` format)
- [ ] Verify your ODBC user has read access to the view (run `SELECT TOP 3 * FROM {view}` in Plex SQL Dev)
- [ ] Add the entry to **both** report YAMLs (prod + test); optionally copy the test YAML to `gs://…/test/` and run the `-test` job to try it
- [ ] Check BigQuery for the new table: `bq query --nouse_legacy_sql "SELECT COUNT(*) FROM \`voxdatalake.PlexTest.{table}\`"`
- [ ] Decide: full refresh or incremental? (does the view have a timestamp column?)
- [ ] If adding a new report: add the GCS objects, both Cloud Run jobs and all four schedulers to `main.tf`, and the jobs to `_ALL_JOBS` in `deploy/cloudbuild.yaml`
- [ ] Commit with `CHANGELOG.md` + `docs/reports/` doc, merge to `main`, `./scripts/deploy.sh`
- [ ] Test the BigQuery VIEW if you added `bq_view` to the YAML
- [ ] Verify row counts and spot-check a few rows against Plex
