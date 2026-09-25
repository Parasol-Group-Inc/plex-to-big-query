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

13 pipelines, 26 Cloud Run jobs (prod + test), 68 BigQuery views. Schedule
for all of them: [EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md).

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
```

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

BigQuery autodetects schema when tables first populate. Empty tables get all-STRING schema; populated tables get proper types (INT64, FLOAT64). If one table populates before another, a JOIN on uncast columns throws a type error.

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
| `google_cloud_scheduler_job` × 4 | `etl_sales_quotes`, `etl_sales_quotes_retry`, `etl_sales_quotes_test`, `etl_sales_quotes_test_retry` | `name` (`plex-<pipeline>-sync[-test][-retry]`), the job reference in `uri`, and the two main `schedule` crons (Mountain time, `var.scheduler_time_zone`) — pick a free 10-minute slot from [EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md). Retries keep `var.retry_scheduler_cron`. |

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
| Cloud Run jobs (13 pipelines) | `plex-etl-<pipeline>` — e.g. `plex-etl-sales-orders` (7:00 PM Mountain) | `plex-etl-<pipeline>-test` — e.g. `plex-etl-sales-orders-test` (7:10 PM Mountain) |
| Schedulers | `plex-<pipeline>-sync` | `plex-<pipeline>-sync-test` |
| Every job's time | [EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md) | |
| Failure retry (all 26 jobs) | 9:45 PM Mountain daily (`plex-<pipeline>-sync[-test]-retry`) — see [Failure Retry](#failure-retry-945-pm-mountain) below | |
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

## Email Status Levels

Every run sends an email with one of three status badges:

| Badge | Color | Meaning |
|---|---|---|
| **SUCCESS** | Green | All extractions completed, all rows written |
| **PARTIAL** | Yellow | One or more extractions failed (ODBC error, BQ write error); other extractions completed successfully — check Events and Errors sections |
| **FAILED** | Red | Job crashed before completing — ODBC connection refused, config load failed, BigQuery unreachable |

For known error signatures (e.g. a specific ODBC error code), the Errors section adds a short 💡 hint in blue explaining what it means and whether it needs Plex Support or a config fix on our side — see `_KNOWN_ERROR_HINTS` in `email_utils.py` to add more as new error patterns get diagnosed.

> A PARTIAL run is not a silent failure — the email lists every failed extraction in the Errors section. Any rows that did succeed are still in BigQuery. The BigQuery VIEW still runs against whatever data is available. If the VIEW was refreshed while some extractions failed, the Events list includes an explicit warning that some source tables hold stale data.

---

## Failure Retry (9:45 PM Mountain)

All 26 jobs have a second Cloud Scheduler trigger that fires daily at **9:45 PM
`America/Denver`** (handles the MST/MDT switch automatically — no manual
adjustment needed). The naming is uniform — `plex-<pipeline>-sync-retry`
retries `plex-etl-<pipeline>`, `plex-<pipeline>-sync-test-retry` retries
`plex-etl-<pipeline>-test`:

| Retry scheduler | Retries |
|---|---|
| `plex-sales-orders-sync-retry` | `plex-etl-sales-orders` (prod) |
| `plex-sales-orders-sync-test-retry` | `plex-etl-sales-orders-test` (test) |
| `plex-work-orders-sync-retry` | `plex-etl-work-orders` (prod) |
| … one pair per pipeline, 52 schedulers in all | |

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

> **Caution — "today" is the UTC date, and some jobs run after the retry.**
> `run_date` and the check both use UTC. A job scheduled *after* 9:45 PM
> Mountain (sales quotes, sales returns, quality supplier returns, and
> `plex-etl-purchasing-pending-requisitions-test` at 9:50 PM), or one whose
> scheduled runs land on the previous UTC day (Label Design, 9:30 AM / 1:30 PM),
> has no "scheduled run today" when its retry fires — so, reading the code, the
> retry does a full run and sends an email every night. Confirm against
> `job_run_log` (query below, `run_mode = 'retry'`) before relying on the
> retry for those pipelines.

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
gcloud scheduler jobs pause plex-sales-orders-sync-retry --location=us-central1 --project=voxdatalake
gcloud scheduler jobs resume plex-sales-orders-sync-retry --location=us-central1 --project=voxdatalake
```

**Changing the retry time/timezone:** edit `retry_scheduler_cron` /
`retry_time_zone` in `terraform.tfvars` (live values: `"45 21 * * *"` /
`"America/Denver"`; the `variables.tf` defaults are `"0 6 * * *"` /
`"America/Denver"`) — applies to all 26 retry schedulers at once — back up
`terraform.tfvars` (its header has the command), then `./scripts/deploy.sh`
from the primary folder. `terraform.tfvars` exists only there.

---

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
