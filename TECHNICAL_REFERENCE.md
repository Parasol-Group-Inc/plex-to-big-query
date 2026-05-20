# Technical Reference

---

## Data flow

### Local mode (`OUTPUT_MODE=local`)

1. Container starts; reads all env vars from `.env` (loaded by docker-compose)
2. `OUTPUT_MODE=local` is set by docker-compose, overriding anything in `.env`
3. `get_credential()` reads `PLEX_ODBC_USER`, `PLEX_ODBC_PASSWORD`, `PLEX_COMPANY_CODE` directly from env — Secret Manager is never called
4. `last_sync` is set to epoch (`1970-01-01T00:00:00Z`) — every local run is a full extract
5. `pyodbc.connect()` establishes a connection using the DSN defined in `config/odbc.ini`
6. SQL query runs with epoch as the `Modified_Date` filter, returning all rows
7. DataFrame is written to `/output/TABLE_NAME_YYYYMMDDTHHMMSSZ.csv`
8. Container exits

### BigQuery mode (`OUTPUT_MODE=bigquery`)

1. Container starts; reads env vars from Cloud Run job definition
2. `get_credential()` checks for direct env var first; falls back to Secret Manager if not found
3. `bigquery.Client` is initialized; `ensure_metadata_table()` creates `sync_metadata` if it does not exist
4. `get_last_sync()` queries `sync_metadata` for `MAX(max_modified_at)` where `table_name = BQ_TABLE`; returns epoch on first run
5. Backfill window (`BACKFILL_MINUTES`) is subtracted from `last_sync` to produce `query_cutoff`
6. `pyodbc.connect()` establishes connection; `CompanyCode` is injected in the connection string (not in `odbc.ini`)
7. SQL query runs with `query_cutoff` as the filter
8. DataFrame is appended to BigQuery via `load_table_from_dataframe` with `WRITE_APPEND`
9. `update_last_sync()` inserts a row into `sync_metadata` recording `max(Modified_Date)` and row count
10. `send_report()` sends a SendGrid email if `SENDGRID_ENABLED=true`

---

## Environment variable reference

| Variable | Default | Mode | Required | Description |
|---|---|---|---|---|
| `OUTPUT_MODE` | `bigquery` | both | no | `local` writes CSVs; `bigquery` writes to BQ |
| `OUTPUT_DIR` | `/output` | local | no | Host-mounted directory for CSV files |
| `PLEX_ODBC_USER` | — | both | yes | Plex ODBC username (bypasses Secret Manager) |
| `PLEX_ODBC_PASSWORD` | — | both | yes | Plex ODBC password (bypasses Secret Manager) |
| `PLEX_COMPANY_CODE` | — | both | yes | Plex CompanyCode (bypasses Secret Manager) |
| `PLEX_DSN` | `PlexProduction` | both | no | DSN name — must match a section in `odbc.ini` |
| `BACKFILL_MINUTES` | `5` | bigquery | no | Minutes to subtract from `last_sync` |
| `GCP_PROJECT` | `""` | bigquery | yes | GCP project ID |
| `BQ_DATASET` | `""` | bigquery | yes | BigQuery dataset name |
| `BQ_TABLE` | `plex_extract` | both | no | Target BQ table (also CSV filename prefix in local mode) |
| `METADATA_TABLE` | `sync_metadata` | bigquery | no | Table that tracks incremental sync state |
| `SECRET_ODBC_USER` | `plex-odbc-user` | bigquery | no | Secret Manager secret name for ODBC username |
| `SECRET_ODBC_PASSWORD` | `plex-odbc-password` | bigquery | no | Secret Manager secret name for ODBC password |
| `SECRET_COMPANY_CODE` | `plex-company-code` | bigquery | no | Secret Manager secret name for CompanyCode |
| `SENDGRID_ENABLED` | `false` | bigquery | no | Set to `true` to enable email reporting |
| `SENDGRID_API_KEY` | — | bigquery | if enabled | SendGrid API key |
| `REPORT_FROM_EMAIL` | — | bigquery | if enabled | Sender email address |
| `REPORT_TO_EMAILS` | — | bigquery | if enabled | Comma-separated list of recipient addresses |
| `REPORT_SUBJECT` | `Plex to BigQuery ETL Report` | bigquery | no | Email subject line |
| `REPORT_TEMPLATE` | `report.html` | bigquery | no | HTML template filename inside `templates/` |

---

## Incremental sync logic

The pipeline avoids re-processing rows it has already loaded by tracking a high-water mark in the `sync_metadata` table.

**On every BigQuery mode run:**

1. `get_last_sync()` reads `MAX(max_modified_at)` from `sync_metadata` for the current `BQ_TABLE`
2. `BACKFILL_MINUTES` (default 5) is subtracted from that timestamp to produce `query_cutoff`
3. The SQL query filters `WHERE Modified_Date > query_cutoff`
4. After a successful write, `update_last_sync()` records `MAX(Modified_Date)` from the new rows

**Why the backfill window exists:**

Plex may assign a `Modified_Date` that is slightly behind wall-clock time at the moment the record is committed. If the ETL ran at exactly the same instant a record was being written, the record's timestamp might fall just before the cutoff. Subtracting 5 minutes ensures those edge rows are captured on the next run. Rows with timestamps in the overlap window that were already loaded appear as duplicates in BigQuery — this is acceptable for most reporting use cases.

**First run behavior:**

If `sync_metadata` is empty (first run or table was cleared), `get_last_sync()` returns `1970-01-01T00:00:00Z`, causing a full table extract.

---

## `sync_metadata` table schema

| Column | Type | Description |
|---|---|---|
| `table_name` | STRING | The `BQ_TABLE` value — allows tracking multiple tables in one metadata table |
| `last_sync_at` | TIMESTAMP | Wall-clock UTC time when the ETL job ran |
| `max_modified_at` | TIMESTAMP | Highest `Modified_Date` value seen in the rows written this run |
| `rows_written` | INTEGER | Number of rows appended to the target table in this run |
| `synced_at` | TIMESTAMP | UTC timestamp when the metadata row was inserted |

Rows accumulate over time — one row per successful run. Use `MAX(max_modified_at)` or `ORDER BY synced_at DESC LIMIT 1` to get the current state.

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
    ▼
DataDirect OpenAccess SDK 8.1  (/usr/oaodbc81/lib64/ivoa27.so)
    │
    ▼
Plex ERP ODBC endpoint  (odbc.plex.com:19995, TLS encrypted)
```

**Key configuration files:**

- `config/odbcinst.ini` — registers the driver name `[DataDirect OpenAccess SDK 8.1]` and points to `ivoa27.so`. Copied to `/etc/odbcinst.ini` in the container.
- `config/odbc.ini` — defines DSNs `[PlexProduction]` and `[PlexTest]` with host, port, and connection settings. Copied to `/etc/odbc.ini` in the container.

**CompanyCode injection:**

`CompanyCode` is NOT stored in `odbc.ini`. It is injected at runtime in `get_odbc_connection()` via the `CustomProperties` field of the connection string:

```python
conn_str = f"DSN={PLEX_DSN};UID={user};PWD={password};CustomProperties=CompanyCode={company_code};"
```

This allows the same Docker image to connect to different Plex company accounts by changing the credential env vars.

**32-bit compatibility:**

The Plex 64-bit driver package bundles `rscshell`, a 32-bit utility. The Dockerfile installs `libc6:i386`, `libncurses5:i386`, and `libstdc++6:i386` to satisfy its dependencies. The main driver (`ivoa27.so`) itself is 64-bit.

---

## Replacing the placeholder SQL query

The `query_plex()` function in `main.py` ships with a placeholder query. It will not return real data until replaced with an actual Plex view or report.

**Steps:**

1. Get the exact view or report name from your Plex support contact (e.g., `Shipping_v_Shipment_Detail`)
2. Ask Plex support for the available column list for that view
3. Open `main.py` and find `query_plex()`
4. Replace the `SELECT` column list and `FROM` clause:

```python
sql = f"""
    SELECT
        S.Shipment_No,
        S.Part_No,
        S.Quantity_Shipped,
        S.Ship_Date,
        S.Modified_Date        ← keep or rename to match actual timestamp column
    FROM
        Shipping_v_Shipment_Detail AS S
    WHERE
        S.Modified_Date > ?    ← keep the ? parameter — this is the incremental filter
    ORDER BY
        S.Modified_Date ASC
"""
```

5. If the timestamp column has a different name than `Modified_Date`, also update this line in `main()`:

```python
if not df.empty and "Modified_Date" in df.columns:
```

and the `max_modified` calculation further down in the same function.

---

## BigQuery schema considerations

**Current behavior:** `autodetect=True` in `write_to_bigquery()` lets BigQuery infer the schema from the DataFrame on each load.

**Risk:** If a column contains only nulls in one run, BigQuery may infer the wrong type. On a later run with actual values, the append will fail with a schema mismatch.

**Recommendation for production:** Define an explicit schema and set `autodetect=False`:

```python
job_config = bigquery.LoadJobConfig(
    write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    schema=[
        bigquery.SchemaField("Part_No",         "STRING"),
        bigquery.SchemaField("Quantity",         "INTEGER"),
        bigquery.SchemaField("Modified_Date",    "TIMESTAMP"),
        # ... add all columns
    ],
)
```

**Duplicate rows:** `WRITE_APPEND` means if a job is retried, rows can be written twice. For append-only reporting workloads this is usually acceptable. For unique-record requirements, add a staging table and use a `MERGE` statement on a business key.

---

## GCP infrastructure reference

| Terraform resource | Type | Purpose |
|---|---|---|
| `google_project_service.required` | API enablement | Enables Cloud Run, Scheduler, BigQuery, Secret Manager, Artifact Registry, Cloud Build, IAM |
| `google_service_account.etl` | IAM | Service account used by the Cloud Run job |
| `google_project_iam_member.etl_roles` | IAM | Grants BQ Editor, BQ Job User, Secret Accessor, AR Reader, Run Invoker |
| `google_service_account_iam_member.scheduler_token_creator` | IAM | Allows Cloud Scheduler to create tokens for the service account |
| `google_bigquery_dataset.plex` | BigQuery | Dataset that holds all Plex tables |
| `google_bigquery_table.sync_metadata` | BigQuery | Incremental sync state tracking table |
| `google_artifact_registry_repository.etl` | Artifact Registry | Docker image repository |
| `google_secret_manager_secret.odbc_user` | Secret Manager | Container for the Plex ODBC username |
| `google_secret_manager_secret.odbc_password` | Secret Manager | Container for the Plex ODBC password |
| `google_secret_manager_secret.company_code` | Secret Manager | Container for the Plex CompanyCode |
| `google_cloud_run_v2_job.etl` | Cloud Run | The ETL job container (600s timeout, max 3 retries) |
| `google_cloud_scheduler_job.etl` | Cloud Scheduler | HTTP trigger on cron schedule |

---

## Cloud Build CI/CD pipeline

`deploy/cloudbuild.yaml` automates the build-push-deploy cycle on every commit to `main`.

**Steps in order:**

1. **fetch-driver** — copies the Plex ODBC driver files from `gs://PROJECT_ID-build-assets/plex-odbc-driver/` into the workspace. This avoids committing binary driver files to git.
2. **build** — runs `docker build`, tagging the image with both the short commit SHA and `latest`
3. **push-sha** — pushes the SHA-tagged image to Artifact Registry
4. **push-latest** — pushes the `latest` tag
5. **deploy** — runs `gcloud run jobs update` with the new SHA-tagged image
6. **smoke-test** — executes the Cloud Run job once and waits for it to complete

The smoke test means every push to `main` triggers a real Plex query. If you want to skip this in development branches, remove or conditionally disable the `smoke-test` step.

---

## File structure reference

```
plex-to-big-query/
├── main.py                      ETL entry point
├── email_utils.py               SendGrid email report builder
├── requirements.txt             Pinned Python dependencies
├── Dockerfile                   Linux container definition
├── docker-compose.yml           Local Phase 1 runner
├── .env.example                 Environment variable template
├── .env                         Your local credentials (gitignored)
├── .gitignore
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
│   │   ├── ddtrc27.so           Trace library
│   │   └── (other .so files)
│   ├── rscshell                 32-bit utility
│   └── etc/lang/                Driver locale files
│
├── terraform/
│   ├── main.tf                  All GCP resources
│   ├── variables.tf             Input variable definitions
│   ├── outputs.tf               Post-apply copy-paste commands
│   ├── terraform.tfvars.example Template for your tfvars file
│   └── terraform.tfvars         Your GCP config (gitignored)
│
├── deploy/
│   ├── setup.sh                 Manual GCP setup — deprecated, use Terraform
│   └── cloudbuild.yaml          Cloud Build CI/CD pipeline
│
└── output/                      CSV files from local runs (gitignored)
```
