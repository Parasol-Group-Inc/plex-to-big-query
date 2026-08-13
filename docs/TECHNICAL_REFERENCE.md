# Technical Reference

---

## Data flow

### Local mode (`OUTPUT_MODE=local`)

1. Container starts via `entrypoint.sh`; env vars loaded from `.env` by docker-compose
2. `docker-compose.yml` forces `OUTPUT_MODE=local`, overriding `.env`
3. `PLEX_ACCESS_TOKEN` is detected → IAM token auth path is used
4. `last_sync` is set to epoch (`1970-01-01T00:00:00Z`) — local runs are full extracts
5. `pyodbc.connect()` builds a **driver-direct** connection string (see ODBC section below)
6. SQL query runs against the configured Plex view
7. DataFrame is written to `/output/BQ_TABLE_YYYYMMDDTHHMMSSZ.csv`
8. Container exits

### BigQuery mode (`OUTPUT_MODE=bigquery`)

1. Container starts; env vars from Cloud Run job definition
2. IAM token is read from Secret Manager via `get_secret(SECRET_TOKEN)`
3. `bigquery.Client` is initialized; `ensure_metadata_table()` creates `sync_metadata` if needed
4. `get_last_sync()` queries `sync_metadata` for `MAX(max_modified_at)` where `table_name = BQ_TABLE`; returns epoch on first run
5. `pyodbc.connect()` establishes a driver-direct connection using the IAM token
6. SQL query runs: `SELECT * FROM {PLEX_VIEW} {PLEX_FILTER} ORDER BY {PLEX_DATE_COL}`
7. For full-refresh tables (no `PLEX_DATE_COL`): `WRITE_TRUNCATE` replaces the table atomically
8. For incremental tables (`PLEX_DATE_COL` set): `WRITE_APPEND` and `sync_metadata` updated
9. `send_report()` in `email_utils.py` sends a SendGrid email if `SENDGRID_ENABLED=true`

---

## Python scripts

### `main.py` — ETL entry point

This is the only script that runs when the container starts. It orchestrates every step.

**Top section — config:** All `os.environ.get()` calls live here. Every tunable value is an env var. Nothing is hardcoded except the BigQuery write mode logic.

**`get_secret(name)`** — calls Google Secret Manager and returns the plain-text value. Used for the Plex IAM token, ODBC password, and company code. Credentials never appear in env vars or logs.

**`get_credential(env_var, secret_name)`** — tries a direct env var first, falls back to Secret Manager. Used to let local runs bypass Secret Manager by setting the value directly in `.env`.

**`get_last_sync(bq)`** — reads `MAX(max_modified_at)` from `sync_metadata`. Returns `1970-01-01` if the table is empty (first run = full load). This is the high-water mark for incremental sync.

**`update_last_sync(bq, ...)`** — writes a new row to `sync_metadata` after a successful load, recording how many rows were written and the new high-water mark.

**`ensure_metadata_table(bq)`** — creates `sync_metadata` if it doesn't exist, and adds any missing columns if the schema has evolved. Safe to call on every run.

**`get_odbc_connection(user, password, company_code, access_token)`** — builds the ODBC connection string and calls `pyodbc.connect()`. See the ODBC section for why driver-direct is required.

**`query_plex(conn)`** — builds and executes the SQL query dynamically from `PLEX_VIEW`, `PLEX_FILTER`, and `PLEX_DATE_COL` env vars. Returns a pandas DataFrame.

**`write_to_bigquery(bq, df)`** — loads the DataFrame into BigQuery using `WRITE_TRUNCATE` (full refresh). Returns row count.

**`write_to_csv(df, output_dir, table_name)`** — writes the DataFrame to a timestamped CSV file for local testing.

**`main()`** — the full pipeline: credentials → BigQuery client → ODBC connection → query → write → metadata update. Returns a `result` dict for the email report.

**`run_and_report()`** — wraps `main()` in a try/except, builds the report dict whether the job succeeds or fails, then calls `send_report()`. This is the actual entry point (`if __name__ == "__main__": run_and_report()`).

---

### `email_utils.py` — SendGrid email report builder

Called from `run_and_report()` after every run, regardless of success or failure.

**`send_report(report)`** — the only public function. Takes the report dict from `main()` and sends an HTML email via SendGrid.

Flow inside `send_report()`:
1. Check `SENDGRID_ENABLED` — exit early if `false`
2. Fetch API key: checks `SENDGRID_API_KEY` env var first, then falls back to Secret Manager using the secret named by `SECRET_SENDGRID_KEY`
3. Build the template context — pulls project, dataset, table, Plex view, host, execution name, and constructs the Cloud Run logs URL automatically
4. Build the email subject — one shape per report `category` (e.g. `[Plex ETL] Sales: Sales Orders — 2026-08-13`), or `[Plex ETL] {company_name} — DATE` if the report has no category set. Status (SUCCESS/PARTIAL/FAILED) and PRODUCTION/TEST are deliberately never in the subject — both live in the body only. Can be overridden with `REPORT_SUBJECT` env var
5. Load `templates/report.html`, substitute `{{placeholders}}`, send via `SendGridAPIClient`

**`_render_template(template, context)`** — simple string replacement for `{{key}}` → value. No external template engine needed.

**`_list_to_html(items)`** — converts a list of event strings to a `<ul>` for the email body.

**`_load_template(name)`** — reads the HTML file from `templates/`. Changing the template only requires a Docker rebuild (the file is baked into the image). See the hot-update table below.

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

> **Test vs production host:** `ServerDataSource=ReportDataSource` works on both `vox.test.odbc.plex.com` (test) and `vox.odbc.plex.com` (production) as of 2026-07-20. Production ODBC access has a history of environment-specific issues unrelated to this setting (a `ServerDataSource` lookup failure, then a separate account/session authorization issue) — see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the full incident history if a new one surfaces.

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
4. Rebuild and push the Docker image:

   ```bash
   docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest .
   docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest
   ```

5. Run the job to verify connectivity

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

Changes in this table take effect after `terraform apply` (~30 seconds). No Docker build needed.

| What you're changing | `terraform.tfvars` variable | Notes |
|---|---|---|
| Plex host (test vs production) | `plex_host` | |
| Which Plex view to query | `plex_view` | |
| SQL WHERE filter | `plex_filter` | Include the word `WHERE` |
| Timestamp column for incremental sync | `plex_date_col` | Empty = full refresh |
| ODBC username | `plex_odbc_user` | |
| Target BigQuery table name | `bq_table` | |
| BigQuery dataset | `bq_dataset` | |
| Email on/off | `sendgrid_enabled` | `"true"` or `"false"` |
| Sender email | `report_from_email` | Must be verified in SendGrid |
| Recipients | `report_to_emails` | Comma-separated |
| Company name in email subject | `company_name` | |
| Backfill window | `backfill_minutes` | Number |
| Cron schedule | `scheduler_cron` | Cron syntax |

**Secrets rotate with a single command — no Terraform, no rebuild:**

```bash
# Rotate the Plex IAM token
echo -n 'NEW_TOKEN' | gcloud secrets versions add plex-access-token \
  --data-file=- --project=voxdatalake

# Rotate the SendGrid API key
echo -n 'SG.new-key' | gcloud secrets versions add sendgrid-api-key \
  --data-file=- --project=voxdatalake
```

### Changes that DO require a Docker rebuild

| What changed | Rebuild command |
|---|---|
| `main.py` | `docker build … && docker push …` |
| `email_utils.py` | `docker build … && docker push …` |
| `templates/report.html` | `docker build … && docker push …` |
| `requirements.txt` (new Python package) | `docker build … && docker push …` |
| `driver/` (new ODBC driver version) | `docker build … && docker push …` |
| `config/odbcinst.ini` or `config/odbc.ini` | `docker build … && docker push …` |

**Not true as of 2026-08-13** — pushing a new image alone does NOT update any deployed job. Cloud Run Jobs resolve their image to a digest at *update* time, not per-execution, and every `google_cloud_run_v2_job` now has `lifecycle { ignore_changes = [image] }` so Terraform won't pick it up either. After pushing, you must explicitly run:
```bash
gcloud run jobs update JOB_NAME --image=us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:TAG --region=us-central1
```
for every job you want on the new image — `deploy/cloudbuild.yaml`'s `deploy-all` step does this for all 16 in one go. Always use a commit-SHA tag, never `:latest`.

---

## Environment variable reference

| Variable | Default | Hot-update? | Description |
|---|---|---|---|
| `OUTPUT_MODE` | `bigquery` | rebuild | `local` = CSV files; `bigquery` = BigQuery write |
| `GCP_PROJECT` | `""` | apply | GCP project ID |
| `BQ_DATASET` | `""` | apply | BigQuery dataset name |
| `BQ_TABLE` | `plex_extract` | apply | Target BigQuery table |
| `METADATA_TABLE` | `sync_metadata` | apply | Sync state tracking table |
| `PLEX_HOST` | `""` | apply | Plex ODBC hostname |
| `PLEX_PORT` | `19995` | apply | Plex ODBC port |
| `PLEX_SERVER_DATASOURCE` | `ReportDataSource` | apply | Server-side data source name |
| `PLEX_ODBC_USER` | `""` | apply | Plex login (`username.company`) |
| `PLEX_DSN` | `PlexProduction` | apply | DSN name for password auth fallback |
| `PLEX_VIEW` | `Part_v_Part` | apply | Plex view or stored procedure to query |
| `PLEX_FILTER` | `""` | apply | SQL WHERE clause (include the word `WHERE`) |
| `PLEX_DATE_COL` | `""` | apply | Timestamp column for incremental sync |
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
| `REPORT_TO_EMAILS` | `""` | apply | Comma-separated recipients |
| `REPORT_SUBJECT` | `""` | apply | Override for auto subject. Empty = `[Plex ETL] {category}: {report names} — DATE`, or `[Plex ETL] {company_name} — DATE` with no category set. Status and PRODUCTION/TEST are never in the subject — body only |
| `COMPANY_NAME` | `Parasol` | apply | Company name in the subject's no-category fallback only |
| `CLOUD_RUN_EXECUTION` | set by GCP | — | Execution ID (auto, used to build logs link) |

---

## Active Plex data source

| Field | Value |
|---|---|
| Plex view | `Part_v_Part` |
| Filter | `WHERE Part_Type = 'Raw Materials'` |
| Sync strategy | Full refresh — no date column, table replaced each run |
| `BQ_TABLE` | `raw_Part_v_Part` |
| `PLEX_DATE_COL` | `""` (empty — no incremental tracking) |

Plex exposes its data through views following the naming convention `{Module}_v_{ObjectName}`. To find a view name, look up the data source in the Plex UI and ask Plex support to confirm the ODBC view name and whether your ODBC user has read access.

---

## Sync strategies

### Full refresh (current — `Part_v_Part`)

No date column on the source. The entire table is replaced on each run:
- `write_disposition = WRITE_TRUNCATE`
- `sync_metadata` records the run timestamp as the watermark
- Suitable for reference/master data (parts lists, customer master, etc.)

### Incremental (for tables with a date column)

A timestamp column (e.g. `Modified_Date`, `Ship_Date`) acts as the high-water mark:
- `get_last_sync()` reads `MAX(max_modified_at)` from `sync_metadata`
- `BACKFILL_MINUTES` subtracted to catch late-arriving rows
- `write_disposition = WRITE_APPEND`
- `update_last_sync()` records the new high-water mark after each run

To enable: set `PLEX_DATE_COL = "your_timestamp_column"` in `terraform.tfvars` and apply.

---

## BigQuery schema guidance

**Current behavior:** `autodetect=True` infers schema from the DataFrame on each load.

**Risk:** A column with only nulls in one run gets inferred as `STRING`. When real values arrive later, the append fails with a schema mismatch.

**Recommendation for production:** Define an explicit schema and set `autodetect=False` in `write_to_bigquery()` inside `main.py`.

---

## GCP infrastructure reference

| Terraform resource | Purpose |
|---|---|
| `google_project_service.required` | Enables Cloud Run, Scheduler, BigQuery, Secret Manager, Artifact Registry, IAM APIs |
| `google_service_account.etl` | Service account used by the Cloud Run job |
| `google_project_iam_member.etl_roles` | Grants BQ Editor, BQ Job User, Secret Accessor, AR Reader, Run Invoker |
| `google_bigquery_dataset.plex` | Dataset holding all Plex tables |
| `google_bigquery_table.sync_metadata` | Incremental sync state (used for date-based tables) |
| `google_artifact_registry_repository.etl` | Docker image repository |
| `google_secret_manager_secret.access_token` | Plex IAM access token |
| `google_secret_manager_secret.sendgrid_api_key` | SendGrid API key |
| `google_cloud_run_v2_job.etl` | ETL job container (600s timeout, 3 retries) |
| `google_cloud_scheduler_job.etl` | HTTP trigger on cron schedule |

---

## File structure reference

```
plex-to-big-query/
├── main.py                      ETL pipeline entry point
├── email_utils.py               SendGrid email report builder
├── requirements.txt             Pinned Python dependencies
├── Dockerfile                   Linux container definition
├── entrypoint.sh                Container startup script
├── docker-compose.yml           Local runner (forces OUTPUT_MODE=local)
├── .env.example                 Environment variable template
├── .env                         Local credentials (gitignored)
│
├── config/
│   ├── odbcinst.ini             Registers Plex driver with unixODBC
│   └── odbc.ini                 PlexProduction and PlexTest DSN definitions
│
├── templates/
│   └── report.html              HTML email report template
│
├── driver/                      Plex Linux ODBC driver (gitignored — get from Plex portal)
│   ├── lib64/
│   │   ├── ivoa27.so            Main driver shared object
│   │   ├── ivoa27.ini           Driver config (auth plugins)
│   │   ├── ddtrc27.so           Trace library
│   │   └── (other .so files)
│   ├── rscshell                 32-bit utility (needs i386 libs)
│   └── etc/lang/                Driver locale and error message files
│
├── terraform/
│   ├── main.tf                  All GCP resources
│   ├── variables.tf             Input variable definitions
│   ├── outputs.tf               Post-apply copy-paste commands
│   └── terraform.tfvars.example Template for your tfvars
│
├── docs/
│   ├── QUICKSTART.md            Step-by-step from zero to deployed
│   ├── FRONTEND_GUIDE.md        Architecture study guide with diagrams
│   ├── API_REFERENCE.md         All gcloud / docker / terraform / bq commands
│   ├── OPERATIONS.md            SendGrid setup and adding more Plex tables
│   ├── TROUBLESHOOTING.md       Error cheatsheet — copy-paste fixes
│   └── TEARDOWN.md              Full infrastructure destroy and redeploy
│
└── output/                      CSV files from local runs (gitignored)
```
