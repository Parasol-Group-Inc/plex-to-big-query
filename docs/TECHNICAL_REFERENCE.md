# Technical Reference

> **Read this first if you're new:** the project started as one Cloud Run
> job pulling one Plex view (`Part_v_Part`) into one BigQuery table — the
> "legacy single-view mode" described below. It has since grown into **16
> Cloud Run jobs** running a **multi-report YAML config mode**, each
> producing one or more named BigQuery views from a shared set of raw
> extractions. Both modes are real, live code paths in `main.py` — legacy
> mode still works and is what you get by default if `REPORT_CONFIG_GCS_PATH`
> is unset — but **every deployed job today uses multi-report mode.** If
> you're building something new, start from multi-report mode (see
> `docs/OPERATIONS.md` § "Add a Brand-New Report"), not legacy mode.

---

## Data flow

### Multi-report mode (`REPORT_CONFIG_GCS_PATH` set — what every real job runs)

1. Container starts; env vars from the Cloud Run job definition, including `REPORT_CONFIG_GCS_PATH` (e.g. `gs://voxdatalake-report-configs/reports/work_orders.yaml`)
2. `load_report_config()` downloads and parses that YAML — `report_name`, `category`, `extractions[]`, `bq_view` (single mapping or list)
3. IAM token fetched from Secret Manager; one `pyodbc` connection is opened and reused across every extraction in the file
4. For each entry in `extractions[]`: `validate_extraction()` checks the view/table/filter/date_col are safe identifiers, then `SELECT * FROM {plex_view} {filter} [ORDER BY {date_col}]` runs and writes to its own raw BigQuery table (`WRITE_TRUNCATE` for full refresh, `WRITE_APPEND` + `sync_metadata` update if `date_col` is set) — one extraction failing is logged as a `partial_error` and does **not** stop the others
5. For each entry in `bq_view` (via `bq_view_configs()`): `validate_bq_view()` checks the name/SQL are safe, the `.sql` file is downloaded from GCS, `{gcp_project}`/`{dataset}` placeholders are substituted, and `create_or_replace_bq_view()` runs a `CREATE OR REPLACE VIEW` — again, one bad view doesn't block the others
6. `log_job_run()` writes one row to `job_run_log` recording this run's status — this is what the 6 AM Mountain retry trigger checks before deciding whether to actually do anything (see "Retry mechanism" below)
7. `send_report()` in `email_utils.py` sends a SendGrid email if `SENDGRID_ENABLED=true`, listing every report this run produced by its real `display_name`, not just the raw table name

### Legacy single-view mode (`REPORT_CONFIG_GCS_PATH` unset — no live job uses this)

Still fully functional — this is what runs if you leave `REPORT_CONFIG_GCS_PATH` empty and set `PLEX_VIEW`/`BQ_TABLE`/`PLEX_FILTER` directly instead. Useful for a one-off local test of a single view without writing a YAML file.

1. Container starts; `PLEX_VIEW`, `BQ_TABLE`, `PLEX_FILTER`, `PLEX_DATE_COL` read directly from env vars
2. `get_last_sync()` queries `sync_metadata` for `MAX(max_modified_at)` where `table_name = BQ_TABLE`; returns epoch (`1970-01-01`) on first run
3. `pyodbc.connect()` establishes a driver-direct connection (IAM token or username/password)
4. `query_plex()` runs `SELECT * FROM {PLEX_VIEW} {PLEX_FILTER} ORDER BY {PLEX_DATE_COL}` and returns a DataFrame
5. Full refresh (no `PLEX_DATE_COL`): `WRITE_TRUNCATE`. Incremental (`PLEX_DATE_COL` set): `WRITE_APPEND` + `sync_metadata` updated
6. `send_report()` sends the email — with no `category`/`display_name` to work from, the subject falls back to the bare `report_name` (or `company_name` if that's empty too)

### Local mode (`OUTPUT_MODE=local`) — either config mode, no BigQuery

1. `docker-compose.yml` forces `OUTPUT_MODE=local`, overriding `.env`
2. Same extraction logic as above (multi-report or legacy, whichever config is set), but `write_to_csv()` writes each table to `/output/{table}_{timestamp}.csv` instead of BigQuery
3. No `sync_metadata`, no `job_run_log`, no BigQuery views created — this mode is for verifying a query/connection works, not for testing the full pipeline
4. **Note on empty results:** the CSV writer skips output entirely on 0 rows, which hides column names for a genuinely-empty Plex view. To inspect schema regardless of row count (e.g. confirming a new view's columns before writing SQL against it), import `main` as a module in a throwaway script and read `cursor.description` directly — see `extract_schema_catalog.py` for exactly this pattern at scale, or `docs/NETSUITE_REPORT_BUILD_PLAN.md`'s "How this was confirmed" section for the one-off version.

---

## Python scripts

### `main.py` — ETL entry point

The only script that runs when the container starts. Orchestrates every step for whichever mode is active.

**Top section — config:** every tunable value is an `os.environ.get()` call. Nothing is hardcoded except the write-mode branching logic itself.

**Credentials & BigQuery setup**
- **`get_secret(name)`** — Secret Manager lookup. Used for the Plex IAM token, ODBC password, company code, SendGrid key.
- **`get_credential(env_var, secret_name)`** — direct env var first, Secret Manager fallback. Lets local runs bypass Secret Manager via `.env`.
- **`ensure_metadata_table(bq)`** — creates `sync_metadata` if missing, adds any new columns if the schema evolved. Safe to call every run.
- **`ensure_job_run_log_table(bq)`** — same idea for `job_run_log` (see "Retry mechanism" below).
- **`get_last_sync(bq)` / `update_last_sync(bq, ...)`** — the incremental-sync high-water mark, read before and written after a successful load.

**ODBC & query**
- **`get_odbc_connection(user, password, company_code, access_token)`** — builds the driver-direct connection string, calls `pyodbc.connect()`. See "ODBC architecture" below for why driver-direct (not DSN) is required.
- **`query_plex(conn)`** — legacy mode only: builds and runs the single `SELECT` from `PLEX_VIEW`/`PLEX_FILTER`/`PLEX_DATE_COL`. Returns a DataFrame.
- **`validate_extraction(extraction)`** — multi-report mode: checks one `extractions[]` entry's `plex_view`/`bq_table`/`date_col` are safe identifiers and `filter` contains no `;`/`--`/`/*` before it's interpolated into SQL. The YAML lives in GCS and is editable outside code review, so this boundary matters.

**Multi-report config**
- **`load_report_config(gcs_path)`** — downloads and YAML-parses a report config from GCS.
- **`bq_view_configs(config)`** — normalizes `bq_view` (a single mapping or a list) into always-a-list, so the rest of the code doesn't need to care which form a given YAML used.
- **`validate_bq_view(view_cfg)`** — same boundary check as `validate_extraction`, for a view's `name`/`sql`/`sql_file`.
- **`create_or_replace_bq_view(bq, dataset, name, sql)`** — runs the actual `CREATE OR REPLACE VIEW` DDL.

**Write**
- **`write_to_bigquery(bq, df)`** — loads a DataFrame with `WRITE_TRUNCATE` (or `WRITE_APPEND`, decided by caller). Returns row count.
- **`write_to_csv(df, output_dir, table_name)`** — local-mode CSV writer.

**Retry mechanism**
- **`get_todays_run_status(bq, job_name)`** — queries `job_run_log` for today's most recent `run_mode = 'scheduled'` row's status.
- **`log_job_run(bq, job_name, status, run_mode)`** — writes one row after every run (scheduled or retry), recording the outcome.

**Entry points**
- **`main()`** — the full pipeline for whichever mode is active. Returns a `result` dict feeding the email report.
- **`run_and_report()`** — the real entry point (`if __name__ == "__main__"`). Wraps `main()` in try/except, checks `RUN_MODE=retry` against `get_todays_run_status()` to no-op cleanly if today's scheduled run already succeeded, calls `log_job_run()`, then `send_report()` regardless of outcome.

### `email_utils.py` — SendGrid email report builder

Called from `run_and_report()` after every run, success or failure.

**`send_report(report)`** — the only public function. Takes the report dict from `main()`/`run_and_report()` and sends an HTML + plain-text email via SendGrid.

Flow inside `send_report()`:
1. Check `SENDGRID_ENABLED` — exit early if `false`
2. Fetch API key: `SENDGRID_API_KEY` env var first, then Secret Manager via `SECRET_SENDGRID_KEY`
3. Build the template context — project, dataset, table(s), Plex view, host, execution name; constructs the Cloud Run logs URL automatically
4. Derive `environment` (`PRODUCTION`/`TEST`) from `bq_dataset` (`PlexProd`/`PlexTest`) — **not** from `report_name`, so it can't drift out of sync with which dataset a run actually wrote to
5. Build the subject: one shape per report `category` (e.g. `[Plex ETL] Sales: Sales Orders, Vox | Open Sales Orders — 2026-08-13`), or `[Plex ETL] {company_name} — DATE` if the report has no category. **Status and environment are deliberately never in the subject** — a pipeline can produce several peer reports in one run, and one aggregate SUCCESS/FAILED in the subject would be misleading if only some of them failed. Both live in the body instead. `REPORT_SUBJECT` env var overrides entirely (when set to something other than the literal default placeholder)
6. Build the "Reports Produced" body section from `reports_detail` — one line per `{display_name, table_name}` pair the run produced; empty/omitted for legacy single-view reports with nothing to break out
7. Load `templates/report.html`, substitute `{{placeholders}}`, send via `SendGridAPIClient`

**`_render_template(template, context)`** — simple string replacement for `{{key}}` → value. `*_html`-suffixed keys are pre-built HTML fragments (not escaped); everything else is `html.escape()`d. No external template engine.

**`_list_to_html(items)` / `_list_to_text(items)`** — event/report-line lists → `<ul>` or `- ` bullets.

**`_errors_to_html(items)` / `_errors_to_text(items)`** — like above, plus a plain-English hint appended when the error matches a known Plex/ODBC failure signature (`_KNOWN_ERROR_HINTS` — session-refused, ServerDataSource not found, expired token, etc.) so a non-technical recipient can tell at a glance whether a failure is Plex's to fix or ours. See `docs/TROUBLESHOOTING.md` for the full detail behind each hint.

**`_load_template(name)`** — reads the HTML file from `templates/`. Baked into the image at build time — changing it needs a rebuild (see the hot-update table below).

### `extract_schema_catalog.py` — bulk column-level schema extraction

Not part of the running pipeline — a one-off (re-runnable) tool for building [`catalog/full_schema_catalog.csv`](../catalog/full_schema_catalog.csv): every confirmed-live Plex view's real columns, in one file. Parses every backtick-quoted view name out of `catalog/*.md`, re-derives the full `{Database}_v_{ViewName}` ODBC query name, and runs `SELECT TOP 0 * FROM {view}` against `vox.test.odbc.plex.com` for each — schema metadata only, zero row data pulled. Run via:

```bash
docker compose run --rm etl python extract_schema_catalog.py
```

As of the 2026-08-12 run: 3,391 candidate names parsed → 2,828 confirmed live (~27,800 columns), 563 errored (mostly a parser artifact where a catalog entry already had the DB prefix in it, double-prefixed on re-derivation — not a Plex-side problem). **Check this file before live-querying Plex to confirm a column exists** — it's usually faster than a fresh `SELECT TOP 0`.

---

## Report YAML config format (multi-report mode)

One file per pipeline in `reports/*.yaml` (prod) and `reports/test/*.yaml` (test) — see `reports/work_orders.yaml` for the fullest real example.

```yaml
report_name: work_orders        # internal identifier; NOT what recipients see in the subject
category: Production            # required for a correct subject — see email_utils.py's send_report()
description: "..."              # free text, shown nowhere except this file

extractions:
  - plex_view: Part_v_Job        # Plex ODBC view — always {Database}_v_{ViewName}
    bq_table: raw_Part_v_Job     # destination raw BigQuery table
    filter: ""                   # SQL WHERE clause (include the word WHERE), or "" for all rows
    date_col: ""                 # timestamp column for incremental sync, or "" for full refresh
  # ... one entry per Plex view this pipeline needs ...

bq_view:                         # a single mapping, OR a list of mappings (see below)
  - name: work_orders_report               # BigQuery view name — becomes a real table you can query
    display_name: "Work Orders"            # what shows in the email subject/body — the report's real name
    sql_file: gs://voxdatalake-report-configs/sql/work_orders_view.sql
  - name: mfg_job_schedule_report
    display_name: "MFG Job Schedule"
    sql_file: gs://voxdatalake-report-configs/sql/mfg_job_schedule_view.sql
```

**Why `bq_view` can be a list:** several reports share one extraction run because they're built from the same raw Plex data — e.g. `work_orders.yaml` produces `work_orders_report`, `mfg_job_schedule_report`, and `labeling_open_work_orders_report` from one shared set of `Part_v_Job`/`Part_v_Job_Op`/etc. extractions. Each view is validated and created independently — one bad view doesn't block the others, and this is a technical/cost optimization only. **The views it produces are peer reports, not "one general report plus extras"** — always give each one its own accurate `display_name`, even if one of them (like `work_orders_report` itself) predates the others and has no Reports List entry of its own.

**`category`/`display_name` are what actually drive the email**, not `report_name`/`bq_table`/`name`. A report with no `category` set falls back to a generic company-name-only subject and a body with no "Reports Produced" breakdown — functionally fine, just less informative. Set both on any new report from day one; see `docs/OPERATIONS.md` § "Add a Brand-New Report" for the full walkthrough and `docs/NETSUITE_REPORT_BUILD_PLAN.md` § "Tackling the next NetSuite report" for the NetSuite-parity-specific version of that same process.

---

## Retry mechanism

Every report family has 3 Cloud Scheduler triggers: prod (its own hour, UTC), test (prod hour + 1, UTC), and one shared retry trigger firing **6 AM Mountain** (`America/Denver`, handles MST/MDT automatically) across every job.

The retry trigger runs with `RUN_MODE=retry`. On every run, `run_and_report()`:
1. Calls `get_todays_run_status(bq, job_identity)` — `job_identity` is `CLOUD_RUN_JOB` (auto-set by Cloud Run) or the report's `report_name` as a local-run fallback
2. If today's `run_mode='scheduled'` row in `job_run_log` already shows `success` or `partial` — **no-op**. Logs a `skipped` row and returns immediately, no Plex query, no email
3. If today's scheduled run is missing or shows `failed` — proceeds with a full real run, same as a scheduled trigger would

This means a genuinely failed run gets one automatic retry ~mid-morning; a run that already succeeded (or partially succeeded) is left alone rather than re-run and potentially double-emailed. `job_run_log` schema: `job_name STRING`, `run_date DATE`, `status STRING`, `run_mode STRING`, `logged_at TIMESTAMP` — one row per completed (or skipped) run, in the same dataset as the report's own tables.

---

## ODBC architecture

```
main.py (Python)
    │
    ▼
pyodbc (Python ODBC bridge)
    │
    ▼
unixODBC driver manager  (/etc/odbcinst.ini registers the driver)
    │
    ▼  driver-direct connection string — bypasses DSN lookup
DataDirect OpenAccess SDK 8.1  (/usr/oaodbc81/lib64/ivoa27.so)
    │  TLS encrypted (Encrypted=1)
    ▼
Plex ERP ODBC endpoint  (vox.odbc.plex.com:19995 prod, vox.test.odbc.plex.com:19995 test)
```

### Why driver-direct instead of DSN

unixODBC does **not** forward driver-specific DSN attributes to the DataDirect driver. In particular, `CustomProperties` — which carries the IAM token — is silently dropped when routing through a DSN lookup. This causes error `HY000 / 3059` on the Plex server.

The fix is to pass all connection attributes directly in the connection string using `DRIVER={path}` instead of `DSN=name`. `CustomProperties` is placed **last** in the string so its internal semicolons are not misinterpreted as connection string delimiters.

### IAM connection string (in use)

```
DRIVER={/usr/oaodbc81/lib64/ivoa27.so};
HOST=vox.odbc.plex.com;   ← production; use vox.test.odbc.plex.com for test
PORT=19995;
ServerDataSource=ReportDataSource;
Encrypted=1;
UseLDAP=0;
UID=edominguez.parasol;
PWD=;
CustomProperties=authmethod=iam; accesstoken=<token>
          ↑ no semicolon after this — token is at the end
```

`UID` follows Plex's `username.company` login format. The IAM token authenticates the user; `UID` identifies which company context to open.

> **Test vs production host:** `ServerDataSource=ReportDataSource` works on both `vox.test.odbc.plex.com` (test) and `vox.odbc.plex.com` (production) as of 2026-07-20. Production ODBC access has a history of environment-specific issues unrelated to this setting (a `ServerDataSource` lookup failure, then a separate account/session authorization issue) — see [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the full incident history if a new one surfaces.

### Username/password connection string (fallback)

Still used if `PLEX_ACCESS_TOKEN` is not set:

```
DSN=PlexProduction;UID=<user>;PWD=<password>;CustomProperties=CompanyCode=<code>;
```

---

## ODBC driver — files, location, and updates

### Where the driver files live

The driver is baked into the Docker image during `docker build`. It is not present in the git repo (gitignored).

| File in the repo | Destination inside container | Purpose |
|---|---|---|
| `driver/lib64/ivoa27.so` | `/usr/oaodbc81/lib64/ivoa27.so` | Main ODBC driver shared object |
| `driver/lib64/ddtrc27.so` | `/usr/oaodbc81/lib64/ddtrc27.so` | Trace library |
| `driver/lib64/ivoa27.ini` | `/usr/oaodbc81/lib64/ivoa27.ini` | Driver config (auth plugins, LDAP settings) |
| `driver/rscshell` | `/usr/oaodbc81/rscshell` | 32-bit utility — requires `libc6:i386` |
| `driver/etc/lang/` | `/usr/oaodbc81/etc/lang/` | Driver locale and error message files |
| `config/odbcinst.ini` | `/etc/odbcinst.ini` | Registers the driver path with unixODBC |
| `config/odbc.ini` | `/etc/odbc.ini` | DSN definitions (used for password auth fallback) |

The container env vars that tell the runtime where to find these:

```dockerfile
ENV LD_LIBRARY_PATH=/usr/oaodbc81/lib64     # tells Linux linker where .so files are
ENV ODBCINI=/etc/odbc.ini                   # unixODBC DSN config
ENV ODBCINSTINI=/etc/odbcinst.ini           # unixODBC driver registry
```

### Obtaining the driver

The Plex ODBC driver is a Progress Software DataDirect product distributed through Plex. Download it from the Plex support portal under `Developer Tools → ODBC Driver → Linux 64-bit`. Extract the archive into the `driver/` folder before running `docker build`.

### What happens when the driver is updated

When Plex releases a new driver version (e.g. from `ivoa27` to `ivoa28`):

1. Download the new Linux driver package from the Plex portal
2. Extract it into `driver/` (overwrite existing files)
3. If the `.so` filename changed, update three places:
   - `Dockerfile`: `COPY driver/ /usr/oaodbc81/` stays the same, but check `ENV LD_LIBRARY_PATH`
   - `config/odbcinst.ini` — the `Driver=` path: `Driver=/usr/oaodbc81/lib64/ivoa28.so`
   - `main.py` `get_odbc_connection()` — the connection string: `DRIVER={/usr/oaodbc81/lib64/ivoa28.so}`
4. Rebuild, tag with the current commit SHA (never `:latest` — see `terraform/variables.tf`'s `image_url` description), and push:

   ```bash
   SHA=$(git rev-parse --short HEAD)
   docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA \
                -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest .
   docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA
   docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest
   ```
5. Explicitly redeploy every job — pushing alone does nothing (see "Changes that DO require a Docker rebuild" below):
   ```bash
   gcloud run jobs update JOB_NAME --image=us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA --region=us-central1
   ```
   or run `deploy/cloudbuild.yaml`'s `deploy-all` step, which loops over all 16 jobs from one build.
6. Run a `-test` job to verify connectivity before trusting prod on the new driver

### Driver license

The DataDirect OpenAccess SDK ships with an OEM license tied to the Plex application. The container prints this warning on every run — it is **not blocking**:

```
[DataDirect][ODBC OpenAccess SDK driver] You are not licensed to use this Progress
Software product under the license you have purchased...
```

This warning means the driver detects it is running outside of its primary licensed application context. As long as your Plex subscription includes ODBC access, connectivity works and this warning is cosmetic. If Plex disables ODBC on your account, the connection will fail with a hard error. Contact Plex support to resolve a license issue — it is managed at the Plex account level, not locally.

There is no license file to rotate or renew yourself. It is not a file on disk.

---

## Hot-updatable configuration (no rebuild required)

Changes in this table take effect on the report's **next run** — either immediately (editing a report YAML in GCS, picked up at the start of the next execution) or after `terraform apply` (~30 seconds, for anything that's a Terraform variable rather than YAML).

| What you're changing | Where | Notes |
|---|---|---|
| Which Plex views a report pulls | `reports/*.yaml` → `extractions[]` | Edit in GCS Console or `gcloud storage cp` — no `terraform apply` needed |
| SQL WHERE filter on one extraction | `reports/*.yaml` → `extractions[].filter` | Include the word `WHERE`; no `;`/`--`/`/*` (rejected) |
| Timestamp column for incremental sync | `reports/*.yaml` → `extractions[].date_col` | Empty = full refresh |
| The BigQuery JOIN view's SQL | `reports/sql/*.sql` | `{gcp_project}`/`{dataset}` placeholders substituted at runtime — never hardcode |
| A report's email category/name | `reports/*.yaml` → `category` / `bq_view[].display_name` | Drives the subject and the body's "Reports Produced" section |
| Plex host (test vs production) | `terraform.tfvars` → `plex_host` | apply |
| ODBC username | `terraform.tfvars` → `plex_odbc_user` | apply |
| Email on/off | `terraform.tfvars` → `sendgrid_enabled` | apply |
| Sender / recipients | `terraform.tfvars` → `report_from_email` / `report_to_emails` | apply |
| Company name (subject's no-category fallback) | `terraform.tfvars` → `company_name` | apply |
| Backfill window | `terraform.tfvars` → `backfill_minutes` | apply |
| Cron schedule for a specific job | `terraform/main.tf` → that job's `google_cloud_scheduler_job.schedule` | apply |

**Secrets rotate with a single command — no Terraform, no rebuild:**

```bash
# Rotate the Plex IAM token
echo -n 'NEW_TOKEN' | gcloud secrets versions add plex-access-token \
  --data-file=- --project=voxdatalake

# Rotate the SendGrid API key
echo -n 'SG.new-key' | gcloud secrets versions add sendgrid-api-key \
  --data-file=- --project=voxdatalake
```

### Changes that DO require a Docker rebuild — AND an explicit redeploy

| What changed | Rebuild command |
|---|---|
| `main.py` | `docker build … && docker push …` |
| `email_utils.py` | `docker build … && docker push …` |
| `templates/report.html` | `docker build … && docker push …` |
| `extract_schema_catalog.py` | `docker build … && docker push …` |
| `requirements.txt` (new Python package) | `docker build … && docker push …` |
| `driver/` (new ODBC driver version) | `docker build … && docker push …` |
| `config/odbcinst.ini` or `config/odbc.ini` | `docker build … && docker push …` |

**Pushing a new image is not enough by itself.** Cloud Run Jobs resolve their image to a digest at *update* time, not per-execution, and every `google_cloud_run_v2_job` has `lifecycle { ignore_changes = [image, client, client_version] }` specifically so a routine `terraform apply` can't silently move a job onto a different image either. After pushing, explicitly redeploy:

```bash
gcloud run jobs update JOB_NAME --image=us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:TAG --region=us-central1
```

`deploy/cloudbuild.yaml`'s `deploy-all` step does this for all 16 jobs from one build (see its `_ALL_JOBS` substitution). Always use a commit-SHA tag, never `:latest` — see `terraform/variables.tf`'s `image_url` description for the full reasoning.

---

## Environment variable reference

| Variable | Default | Hot-update? | Description |
|---|---|---|---|
| `OUTPUT_MODE` | `bigquery` | rebuild | `local` = CSV files; `bigquery` = BigQuery write |
| `GCP_PROJECT` | `""` | apply | GCP project ID |
| `BQ_DATASET` | `""` | apply | BigQuery dataset name — also what `email_utils.py` uses to derive the PRODUCTION/TEST body badge |
| `BQ_TABLE` | `plex_extract` | apply | Legacy single-view mode only — target table name |
| `METADATA_TABLE` | `sync_metadata` | apply | Sync state tracking table |
| `JOB_RUN_LOG_TABLE` | `job_run_log` | apply | Retry-tracking table — see "Retry mechanism" |
| `RUN_MODE` | `""` | — | Set to `retry` by the 6 AM Mountain scheduler trigger; anything else runs as a normal scheduled execution |
| `REPORT_CONFIG_GCS_PATH` | `""` | — (edit the YAML instead) | GCS path to the multi-report YAML. Empty = legacy single-view mode using the vars below |
| `PLEX_HOST` | `""` | apply | Plex ODBC hostname |
| `PLEX_PORT` | `19995` | apply | Plex ODBC port |
| `PLEX_SERVER_DATASOURCE` | `ReportDataSource` | apply | Server-side data source name |
| `PLEX_ODBC_USER` | `""` | apply | Plex login (`username.company`) |
| `PLEX_DSN` | `PlexProduction` | apply | DSN name for password auth fallback |
| `PLEX_VIEW` | `Part_v_Part` | apply | Legacy single-view mode only — which view/stored procedure to query |
| `PLEX_FILTER` | `""` | apply | Legacy mode only — SQL WHERE clause (include the word `WHERE`) |
| `PLEX_DATE_COL` | `""` | apply | Legacy mode only — timestamp column for incremental sync |
| `BACKFILL_MINUTES` | `5` | apply | Minutes to subtract from last sync (incremental) |
| `PLEX_ACCESS_TOKEN` | — | secret | IAM token (direct). Normally fetched from Secret Manager. |
| `SECRET_ACCESS_TOKEN` | `plex-access-token` | apply | Secret Manager secret name for the IAM token |
| `SECRET_ODBC_USER` | `plex-odbc-user` | apply | Secret Manager secret name for ODBC username |
| `SECRET_ODBC_PASSWORD` | `plex-odbc-password` | apply | Secret Manager secret name for ODBC password |
| `SECRET_COMPANY_CODE` | `plex-company-code` | apply | Secret Manager secret name for CompanyCode |
| `SENDGRID_ENABLED` | `false` | apply | Set `true` to enable email reports |
| `SENDGRID_API_KEY` | — | secret | SendGrid key (direct). Normally fetched from Secret Manager. |
| `SECRET_SENDGRID_KEY` | `sendgrid-api-key` | apply | Secret Manager secret name for SendGrid key |
| `REPORT_FROM_EMAIL` | `""` | apply | Verified sender address |
| `REPORT_TO_EMAILS` | `""` | apply | Comma-separated recipients — same list for prod and test today, see `docs/EMAIL_SCHEDULE.md`'s "Worth deciding" section |
| `REPORT_SUBJECT` | `""` | apply | Override for auto subject. Empty = `[Plex ETL] {category}: {report names} — DATE`, or `[Plex ETL] {company_name} — DATE` with no category set. Status and PRODUCTION/TEST are never in the subject — body only |
| `COMPANY_NAME` | `Parasol` | apply | Company name in the subject's no-category fallback only |
| `CLOUD_RUN_JOB` | set by GCP | — | Auto-injected job name; used as the retry mechanism's `job_identity` key |
| `CLOUD_RUN_EXECUTION` | set by GCP | — | Execution ID (auto, used to build logs link) |
| `CLOUD_RUN_REGION` | `us-central1` | apply | Used to build the Cloud Console logs URL in the email |

---

## Active report pipelines

The project runs **8 report families × prod/test = 16 Cloud Run jobs**, each on its own hourly-staggered schedule (2 AM through 5 PM UTC, prod/test pairs one hour apart), plus a shared 6 AM Mountain retry trigger for all of them. Full enumerated schedule, real run history, and the category/display_name naming convention: **[docs/EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md)**.

Every pipeline's actual extractions/views are defined in its `reports/*.yaml` — that YAML, not this doc, is the source of truth for what a given job pulls. The single-`Part_v_Part`-view example that used to live in this section was the *original* pipeline (now `plex-etl`/`sales_orders.yaml`, since expanded to 13 extractions + 2 views) — kept as one example rather than duplicated here since it drifts out of sync with reality otherwise (as it already had, for a while).

Plex exposes its data through views following the naming convention `{Module}_v_{ObjectName}`. To find a view for a new report, start with [`catalog/plex_catalog_index.md`](../catalog/plex_catalog_index.md) (per-database view lists) and [`catalog/full_schema_catalog.csv`](../catalog/full_schema_catalog.csv) (confirmed-live columns for ~2,800 views) before querying Plex directly.

---

## Sync strategies

### Full refresh (most extractions today)

No date column on the source. The entire table is replaced on each run:
- `write_disposition = WRITE_TRUNCATE`
- `sync_metadata` records the run timestamp as the watermark
- Suitable for reference/master data (parts lists, customer master, etc.) and anything where the source has no reliable modified-date column

### Incremental (for tables with a date column)

A timestamp column (e.g. `Modified_Date`, `Ship_Date`, `Change_Date`) acts as the high-water mark:
- `get_last_sync()` reads `MAX(max_modified_at)` from `sync_metadata`
- `BACKFILL_MINUTES` subtracted to catch late-arriving rows
- `write_disposition = WRITE_APPEND`
- `update_last_sync()` records the new high-water mark after each run

To enable on a multi-report extraction: set that entry's `date_col` in the YAML. In legacy mode: set `PLEX_DATE_COL` in `terraform.tfvars` and apply.

---

## BigQuery schema guidance

**Current behavior:** `autodetect=True` infers schema from the DataFrame on each load.

**Risk:** A column with only nulls in one run gets inferred as `STRING`. When real values arrive later, the append fails with a schema mismatch — and separately, an empty table gets an all-`STRING` schema, so a `JOIN` on a numeric key between one populated table and one still-empty table throws a type error. Always wrap numeric JOIN keys and aggregated columns in `SAFE_CAST` in report SQL — see `reports/sql/work_orders_view.sql` for the pattern.

**Recommendation for production:** Define an explicit schema and set `autodetect=False` in `write_to_bigquery()` inside `main.py`. Not yet done — every table today is still autodetected.

---

## GCP infrastructure reference

Terraform state lives remotely in `gs://voxdatalake-terraform-state/plex-to-big-query/` (GCS backend, versioning enabled) — any team member with access can safely run `plan`/`apply` from their own machine. `terraform.tfvars` itself is gitignored and only ever exists locally; back it up after every edit (documented in the file's own header) to `gs://voxdatalake-terraform-state/plex-to-big-query/terraform.tfvars.backup`.

| Terraform resource | Purpose |
|---|---|
| `google_project_service.required` | Enables Cloud Run, Scheduler, BigQuery, Secret Manager, Artifact Registry, IAM APIs |
| `google_service_account.etl` | Service account used by every Cloud Run job |
| `google_project_iam_member.etl_roles` | Grants BQ Editor, BQ Job User, Secret Accessor, AR Reader, Run Invoker |
| `google_bigquery_dataset.plex` (+ `_test`) | `PlexProd`/`PlexTest` datasets holding all Plex tables |
| `google_bigquery_table.sync_metadata` | Incremental sync state (used for date-based extractions) |
| `google_storage_bucket.report_configs` | `voxdatalake-report-configs` — holds every `reports/*.yaml`/`reports/sql/*.sql`, editable without a deploy |
| `google_artifact_registry_repository.etl` | Docker image repository |
| `google_secret_manager_secret.access_token` / `.sendgrid_api_key` / etc. | Plex IAM token, ODBC creds, SendGrid key |
| `google_cloud_run_v2_job.etl` (× 16, one per report family × prod/test) | Each job's `containers.image` has `lifecycle { ignore_changes = [image, client, client_version] }` — Terraform intentionally doesn't manage the deployed image; `deploy/cloudbuild.yaml` or a manual `gcloud run jobs update` does |
| `google_cloud_scheduler_job.etl` (× 16 scheduled + 16 retry = 32) | HTTP triggers on cron schedules — see `docs/EMAIL_SCHEDULE.md` for the full enumerated list |

---

## File structure reference

```
plex-to-big-query/
├── main.py                      ETL pipeline entry point (legacy + multi-report modes)
├── email_utils.py                SendGrid email report builder
├── extract_schema_catalog.py     Bulk column-level schema extraction tool (not part of the running pipeline)
├── requirements.txt              Pinned Python dependencies
├── Dockerfile                    Linux container definition
├── entrypoint.sh                 Container startup script
├── docker-compose.yml             Local runner (forces OUTPUT_MODE=local)
├── .env.example                  Environment variable template
├── .env                          Local credentials (gitignored)
│
├── config/
│   ├── odbcinst.ini              Registers Plex driver with unixODBC
│   └── odbc.ini                  PlexProduction and PlexTest DSN definitions
│
├── templates/
│   └── report.html               HTML email report template
│
├── driver/                       Plex Linux ODBC driver (gitignored — get from Plex portal)
│   ├── lib64/
│   │   ├── ivoa27.so              Main driver shared object
│   │   ├── ivoa27.ini              Driver config (auth plugins)
│   │   ├── ddtrc27.so              Trace library
│   │   └── (other .so files)
│   ├── rscshell                   32-bit utility (needs i386 libs)
│   └── etc/lang/                  Driver locale and error message files
│
├── reports/                      One YAML + one SQL per report family (16 YAMLs incl. test/)
│   ├── {report}.yaml               Prod config — extractions[], category, bq_view[]
│   ├── test/{report}.yaml          Test config — same shape, different dataset/host
│   └── sql/{report}_view.sql       BigQuery JOIN SQL for each bq_view entry
│
├── catalog/                      Plex ODBC schema documentation (not runtime-used)
│   ├── plex_catalog_index.md       Per-database view name index
│   ├── plex_*_views_catalog.md     One file per Plex database (Sales, Part, Quality, ...)
│   └── full_schema_catalog.csv     Column-level schema for ~2,800 confirmed-live views
│
├── mapping/                       NetSuite report ↔ Plex mapping worksheets
├── reports-list/                  Company report inventory by department, source-of-truth for `category`/`display_name`
├── spreadsheets/                  Google Sheet → BigQuery mapping docs (MFG Job Schedule, etc.)
│
├── terraform/
│   ├── main.tf                    All GCP resources — 16 Cloud Run jobs, 32 schedulers, buckets, IAM
│   ├── variables.tf                Input variable definitions
│   ├── outputs.tf                  Post-apply copy-paste commands
│   ├── terraform.tfvars.example    Template for your tfvars (tracked in git)
│   └── terraform.tfvars            Your real values (gitignored — back up to GCS, see its header)
│
├── deploy/
│   └── cloudbuild.yaml             Cloud Build CI — builds once, deploys to all 16 jobs
│
├── docs/
│   ├── QUICKSTART.md               Step-by-step from zero to deployed (original single-pipeline walkthrough)
│   ├── DEPLOYMENT_GUIDE.md         Same ground as QUICKSTART, more detail + troubleshooting
│   ├── OPERATIONS.md               Day-to-day: edit a report, add a brand-new report, SendGrid setup
│   ├── EMAIL_SCHEDULE.md           Full 16-job schedule, real run history, naming convention rationale
│   ├── NETSUITE_REPORT_BUILD_PLAN.md  NetSuite-parity report build log + step-by-step for the next one
│   ├── CLICKUP_TEAM_GUIDE.md       Condensed team-facing walkthrough
│   ├── CHEATSHEET.md               Quick-reference commands, condensed "add a report" version
│   ├── FRONTEND_GUIDE.md           Architecture study guide with diagrams
│   ├── API_REFERENCE.md            All gcloud / docker / terraform / bq commands
│   ├── TROUBLESHOOTING.md          Error cheatsheet — copy-paste fixes
│   ├── DISASTER_RECOVERY.md        Full-loss recovery procedure
│   └── TEARDOWN.md                 Full infrastructure destroy and redeploy
│
└── output/                       CSV files from local runs (gitignored)
```
