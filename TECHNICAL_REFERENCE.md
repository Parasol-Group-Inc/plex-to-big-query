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
2. `PLEX_ACCESS_TOKEN` is read from Secret Manager via `get_secret(SECRET_TOKEN)`
3. `bigquery.Client` is initialized; `ensure_metadata_table()` creates `sync_metadata` if needed
4. `get_last_sync()` queries `sync_metadata` for `MAX(max_modified_at)` where `table_name = BQ_TABLE`; returns epoch on first run
5. Backfill window (`BACKFILL_MINUTES`) is subtracted from `last_sync` to produce `query_cutoff`
6. `pyodbc.connect()` establishes a driver-direct connection using the IAM token
7. SQL query runs
8. For full-refresh tables (no date column): `WRITE_TRUNCATE` replaces the table each run
9. For incremental tables (with a date column): `WRITE_APPEND` and `sync_metadata` updated
10. `send_report()` sends a SendGrid email if `SENDGRID_ENABLED=true`

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
Plex ERP ODBC endpoint  (vox.odbc.plex.com:19995 for test / odbc.plex.com:19995 for prod)
```

### Why driver-direct instead of DSN

unixODBC does **not** forward driver-specific DSN attributes to the DataDirect driver. In particular, `CustomProperties` — which carries the IAM token — is silently dropped when routing through a DSN lookup. This causes error `HY000 / 3059: The specified data source is not defined` on the Plex server.

The fix is to pass all connection attributes directly in the connection string using `DRIVER={path}` instead of `DSN=name`. `CustomProperties` is placed **last** in the string so its internal semicolons are not misinterpreted as connection string delimiters.

### IAM connection string (in use)

```
DRIVER={/usr/oaodbc81/lib64/ivoa27.so};
HOST=vox.odbc.plex.com;
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

> **Test vs production host:** `ServerDataSource=ReportDataSource` is confirmed working on `vox.odbc.plex.com` (test host). The production host `odbc.plex.com` returns error `HY000 10300: service not found` — the service name is different on production. Confirm the correct `ServerDataSource` with Plex support before switching to production.

### Username/password connection string (fallback)

Still used if `PLEX_ACCESS_TOKEN` is not set. Routes through the DSN because `CompanyCode` does not need to be inside `CustomProperties` when using standard auth:

```
DSN=PlexProduction;UID=<user>;PWD=<password>;CustomProperties=CompanyCode=<code>;
```

### Key configuration files

| File | Container path | Purpose |
|---|---|---|
| `config/odbcinst.ini` | `/etc/odbcinst.ini` | Registers the DataDirect driver with unixODBC |
| `config/odbc.ini` | `/etc/odbc.ini` | DSN definitions (used for username/password auth only) |
| `driver/lib64/ivoa27.so` | `/usr/oaodbc81/lib64/ivoa27.so` | DataDirect OpenAccess SDK 8.1 main driver |
| `driver/lib64/ivoa27.ini` | `/usr/oaodbc81/lib64/ivoa27.ini` | Driver's own config (auth plugins, LDAP, translit) |
| `entrypoint.sh` | `/entrypoint.sh` | Container startup script |

### DataDirect license

The driver ships with an OEM SDK Client license (serial `004193623`, key `35057920`) tied to the Plex application. When invoked from Python/pyodbc it runs in 15-day trial mode and prints a warning. This does not block connectivity. Resolve before going to production by contacting Progress Software or Plex support for a standalone license.

---

## Environment variable reference

| Variable | Default | Required | Description |
|---|---|---|---|
| `OUTPUT_MODE` | `bigquery` | no | `local` writes CSVs; `bigquery` writes to BQ. docker-compose forces `local`. |
| `OUTPUT_DIR` | `/output` | no | Host-mounted directory for local CSV files |
| `PLEX_ACCESS_TOKEN` | — | **yes** | IAM access token from Plex. Presence triggers IAM auth mode. |
| `PLEX_ODBC_USER` | — | **yes** | Plex login in `username.company` format (e.g. `edominguez.parasol`) |
| `PLEX_HOST` | — | **yes (IAM)** | Plex ODBC hostname. `vox.odbc.plex.com` for test, `odbc.plex.com` for prod |
| `PLEX_PORT` | `19995` | no | Plex ODBC port |
| `PLEX_SERVER_DATASOURCE` | `ReportDataSource` | no | Server-side data source name |
| `PLEX_DSN` | `PlexProduction` | no | DSN name used for username/password auth path only |
| `PLEX_ODBC_PASSWORD` | — | only if no token | Plex ODBC password (username/password auth) |
| `PLEX_COMPANY_CODE` | — | only if no token | Plex CompanyCode (username/password auth) |
| `BACKFILL_MINUTES` | `5` | no | Minutes subtracted from `last_sync` (incremental tables only) |
| `GCP_PROJECT` | `""` | bigquery | GCP project ID |
| `BQ_DATASET` | `""` | bigquery | BigQuery dataset name |
| `BQ_TABLE` | `plex_extract` | no | Target BQ table name; also CSV filename prefix in local mode |
| `METADATA_TABLE` | `sync_metadata` | no | Table tracking incremental sync state |
| `SECRET_ACCESS_TOKEN` | `plex-access-token` | no | Secret Manager secret name for the IAM token |
| `SECRET_ODBC_USER` | `plex-odbc-user` | no | Secret Manager secret name for ODBC username (password auth) |
| `SECRET_ODBC_PASSWORD` | `plex-odbc-password` | no | Secret Manager secret name for ODBC password |
| `SECRET_COMPANY_CODE` | `plex-company-code` | no | Secret Manager secret name for CompanyCode |
| `SENDGRID_ENABLED` | `false` | no | Set `true` to enable email reporting (bigquery mode only) |
| `SENDGRID_API_KEY` | — | if enabled | SendGrid API key |
| `REPORT_FROM_EMAIL` | — | if enabled | Sender address |
| `REPORT_TO_EMAILS` | — | if enabled | Comma-separated recipient list |

---

## Active Plex data source

| Field | Value |
|---|---|
| Plex view | `Part_v_Part` |
| Filter | `WHERE Part_Type = 'Raw Materials'` |
| Sync strategy | Full refresh — no date column, table replaced each run |
| `BQ_TABLE` | `raw_materials_parts` |
| `PLEX_DATE_COL` | `""` (empty — no incremental tracking) |

Plex exposes ~50,000 tables/views via ODBC following the naming convention `{Module}_v_{ObjectName}`. To find a view name, look up the data source in the Plex UI under Data Source Detail and match the stored procedure or view name.

---

## Sync strategies

### Full refresh (current — `Part_v_Part`)

No date column on the source. The entire table is replaced on each run:
- `write_disposition = WRITE_TRUNCATE`
- `sync_metadata` is not updated (no meaningful high-water mark)
- Suitable for reference/master data that changes infrequently

### Incremental (future tables with a date column)

A timestamp column (e.g. `Modified_Date`, `Ship_Date`) acts as the high-water mark:
- `get_last_sync()` reads `MAX(max_modified_at)` from `sync_metadata`
- `BACKFILL_MINUTES` subtracted to catch late-arriving rows
- `write_disposition = WRITE_APPEND`
- `update_last_sync()` records the new high-water mark after each run

To switch a table to incremental: set `PLEX_DATE_COL` to the timestamp column name in `main.py` and ensure `query_plex()` filters `WHERE {date_col} > ?`.

---

## BigQuery schema guidance

**Current behavior:** `autodetect=True` infers schema from the DataFrame on each load.

**Risk:** A column with only nulls in one run gets inferred as `STRING`. When real values arrive later, the append fails with a schema mismatch.

**Recommendation for production:** Define an explicit schema and set `autodetect=False`:

```python
job_config = bigquery.LoadJobConfig(
    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,  # or WRITE_APPEND
    schema=[
        bigquery.SchemaField("Part_No",     "STRING", mode="REQUIRED"),
        bigquery.SchemaField("Rev",         "STRING"),
        bigquery.SchemaField("Name",        "STRING"),
        bigquery.SchemaField("Old_Part_No", "STRING"),
        bigquery.SchemaField("Part_Type",   "STRING"),
        bigquery.SchemaField("Part_Group",  "STRING"),
        bigquery.SchemaField("Part_Status", "STRING"),
        bigquery.SchemaField("Part_Source", "STRING"),
        bigquery.SchemaField("Note",        "STRING"),
    ],
)
```

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
| `google_cloud_run_v2_job.etl` | ETL job container (600s timeout, 3 retries) |
| `google_cloud_scheduler_job.etl` | HTTP trigger on cron schedule |

---

## File structure reference

```
plex-to-big-query/
├── main.py                      ETL entry point
├── email_utils.py               SendGrid email report builder
├── requirements.txt             Pinned Python dependencies
├── Dockerfile                   Linux container definition
├── entrypoint.sh                Container startup (env substitution if needed)
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
├── driver/                      Plex Linux ODBC driver (gitignored)
│   ├── lib64/
│   │   ├── ivoa27.so            Main driver shared object
│   │   ├── ivoa27.ini           Driver config (auth plugins)
│   │   ├── ddtrc27.so           Trace library
│   │   └── (other .so files)
│   ├── rscshell                 32-bit utility (needs i386 libs)
│   └── etc/lang/                Driver locale/message files
│
├── terraform/
│   ├── main.tf                  All GCP resources
│   ├── variables.tf             Input variable definitions
│   ├── outputs.tf               Post-apply copy-paste commands
│   └── terraform.tfvars.example Template for your tfvars
│
├── deploy/
│   ├── setup.sh                 Manual GCP setup (deprecated, use Terraform)
│   └── cloudbuild.yaml          Cloud Build CI/CD pipeline
│
└── output/                      CSV files from local runs (gitignored)
```
