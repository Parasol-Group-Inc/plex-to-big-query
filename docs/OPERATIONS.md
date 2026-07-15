# Operations Guide

Day-to-day operations: editing reports, adding new reports, configuring SendGrid, and managing environments.

---

## How the Report System Works

Reports are defined by **YAML files stored in Cloud Storage** — not hardcoded in the container image or Terraform variables. This means you can change what gets extracted and how the BigQuery view looks without any code deployment.

```
gs://voxdatalake-report-configs/
├── reports/
│   ├── sales_orders.yaml          ← prod: 13 Plex views → PlexProd (2 AM UTC)
│   └── work_orders.yaml           ← prod: 4 Part DB views → PlexProd (4 AM UTC)
├── test/
│   ├── sales_orders.yaml          ← test: same views → PlexTest (3 AM UTC)
│   └── work_orders.yaml           ← test: same views → PlexTest (5 AM UTC)
└── sql/
    ├── sales_orders_view.sql      ← BigQuery JOIN SQL for 16-field sales report ✏
    └── work_orders_view.sql       ← BigQuery JOIN SQL for work orders report ✏
```

**Each YAML file contains:**
- `extractions[]` — list of Plex views to pull, with optional filters and destination table names
- `bq_view` — optional BigQuery VIEW definition (the SQL that JOINs raw tables into the report)

The Cloud Run Job reads the YAML at startup on every run. The `REPORT_CONFIG_GCS_PATH` env var tells it which YAML to load.

---

## Edit an Existing Report (No Deployment)

### Change a filter on a Plex view

1. Edit `reports/sales_orders.yaml` — find the extraction you want to filter and set the `filter` field:

```yaml
extractions:
  - plex_view: Sales_v_PO
    bq_table: raw_Sales_v_PO
    filter: "WHERE PO_Status_Key = 2073"   # ← add filter here
    date_col: ""
```

2. Push to GCS:

```bash
gcloud storage cp reports/sales_orders.yaml gs://voxdatalake-report-configs/reports/
```

3. Trigger a run:

```bash
gcloud run jobs execute plex-etl-test \
  --region=us-central1 --project=voxdatalake --wait
```

### Add a Plex view to an existing report

Add a new entry to the `extractions[]` list in the YAML:

```yaml
  - plex_view: Sales_v_PO_Type        # ← Plex view name (always {DB}_v_{View})
    bq_table: raw_Sales_v_PO_Type     # ← BigQuery table name (choose anything)
    filter: ""                         # ← WHERE clause, or "" for all rows
    date_col: ""                       # ← timestamp column for incremental, or ""
```

Then push and trigger as above.

### Change the BigQuery JOIN view SQL

The `sales_orders_view.sql` file defines the 16-field report. Edit it and push:

```bash
# Edit reports/sql/sales_orders_view.sql locally, then:
gcloud storage cp reports/sql/sales_orders_view.sql \
  gs://voxdatalake-report-configs/sql/

# The next pipeline run will CREATE OR REPLACE the view in BigQuery.
# You can also edit the view directly in the BigQuery Console —
# your changes persist until the next pipeline run.
gcloud run jobs execute plex-etl-test \
  --region=us-central1 --project=voxdatalake --wait
```

> **Note on SQL placeholders:** The SQL file uses `{gcp_project}` and `{dataset}` which the container replaces at runtime with the `GCP_PROJECT` and `BQ_DATASET` env var values. Never hardcode `voxdatalake` or `PlexProd` in the SQL file — it must work for both prod and test.

---

## Add a Brand-New Report

This is the full end-to-end process. Use `work_orders` as a reference implementation — its files are the most up-to-date example of every pattern in use.

### Step 0 — Find the right Plex views

Before writing any code, verify the views exist and contain the columns you need.

1. Open **Plex SQL Developer** (or the ODBC query tool)
2. Browse the database tree — views are named `{Database}_v_{ViewName}` (e.g., `Part_v_Job`, `Sales_v_PO`)
3. Run `SELECT TOP 5 * FROM {view}` to confirm columns and data types
4. Check [`catalog/plex_catalog_index.md`](../catalog/plex_catalog_index.md) for a cross-database index of known views

> **No aliases in FROM clause.** Plex SQL Developer rejects trailing table aliases (`FROM Part_v_Job j`). Use the full view name every time.

> **No "Prod" database.** Work orders, jobs, and manufacturing data live in the **Part** database, not a "Prod" database. Check the catalog before assuming where a view lives.

### Step 1 — Create the YAML

```bash
cp reports/work_orders.yaml reports/purchasing_orders.yaml
cp reports/test/work_orders.yaml reports/test/purchasing_orders.yaml
```

Edit `reports/purchasing_orders.yaml`:

```yaml
report_name: purchasing_orders
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
  sql_file: gs://voxdatalake-report-configs/sql/purchasing_orders_view.sql
```

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

### Step 3 — Create a test YAML in GCS and push all files

```bash
# Push prod config
gcloud storage cp reports/purchasing_orders.yaml \
  gs://voxdatalake-report-configs/reports/ --project=voxdatalake

# Push test config
gcloud storage cp reports/test/purchasing_orders.yaml \
  gs://voxdatalake-report-configs/test/ --project=voxdatalake

# Push SQL
gcloud storage cp reports/sql/purchasing_orders_view.sql \
  gs://voxdatalake-report-configs/sql/ --project=voxdatalake
```

### Step 4 — Add Cloud Run Jobs in `terraform/main.tf`

Copy the `etl_work_orders` and `etl_work_orders_test` blocks. The only required changes per report are: job name, `REPORT_CONFIG_GCS_PATH`, `BQ_DATASET`, `PLEX_HOST`, and schedule.

```hcl
resource "google_cloud_run_v2_job" "etl_purchasing" {
  name     = "plex-etl-purchasing"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      max_retries     = 1
      timeout         = "600s"
      containers {
        image = var.image_url
        env { name = "GCP_PROJECT";            value = var.gcp_project }
        env { name = "BQ_DATASET";             value = var.bq_dataset }      # "PlexProd"
        env { name = "PLEX_HOST";              value = var.plex_host }        # prod host
        env { name = "PLEX_PORT";              value = "19995" }
        env { name = "PLEX_SERVER_DATASOURCE"; value = "ReportDataSource" }
        env { name = "REPORT_CONFIG_GCS_PATH"
              value = "gs://${var.report_configs_bucket}/reports/purchasing_orders.yaml" }
        env { name = "METADATA_TABLE";         value = var.metadata_table }
        env { name = "SENDGRID_ENABLED";       value = var.sendgrid_enabled }
        env { name = "REPORT_FROM_EMAIL";      value = var.report_from_email }
        env { name = "REPORT_TO_EMAILS";       value = var.report_to_emails }
        env { name = "SECRET_SENDGRID_KEY";    value = var.secret_sendgrid_key }
        env { name = "SECRET_ACCESS_TOKEN";    value = var.secret_access_token }
        env { name = "COMPANY_NAME";           value = var.company_name }
        env { name = "REPORT_SUBJECT";         value = var.report_subject }
      }
    }
  }
}

resource "google_cloud_scheduler_job" "etl_purchasing" {
  name      = "plex-purchasing-sync"
  schedule  = "0 6 * * *"   # pick a time after your upstream reports finish
  time_zone = "UTC"
  region    = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_purchasing.name}:run"
    body        = base64encode("{}")
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

# Repeat for the test job — change: name, BQ_DATASET=PlexTest, PLEX_HOST=plex_host_test,
# REPORT_CONFIG_GCS_PATH=.../test/purchasing_orders.yaml, schedule cron
```

> **Note on `BQ_TABLE` and `PLEX_VIEW`:** these env vars are only used in the legacy single-view mode and have no effect when `REPORT_CONFIG_GCS_PATH` is set. You don't need to set them for new multi-report pipelines.

### Step 5 — Apply Terraform and deploy the image

```bash
# If you changed Python code (main.py, email_utils.py):
gcloud builds submit \
  --config deploy/cloudbuild.yaml \
  --project=voxdatalake \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)

# Infrastructure only (YAML/SQL + new Cloud Run jobs):
cd terraform && terraform apply -var-file=terraform.tfvars
```

> **Cloud Build safety:** the build's smoke test runs **`plex-etl-test`
> only** (writes to `PlexTest`). Production is never executed automatically —
> after the test run looks good, trigger prod yourself:
> `gcloud run jobs execute plex-etl --region=us-central1`

### Step 6 — Test and validate

```bash
# Trigger test job
gcloud run jobs execute plex-etl-purchasing-test \
  --region=us-central1 --project=voxdatalake --wait

# Preview the BQ view (BigQuery Console or bq.cmd):
# SELECT * FROM `voxdatalake.PlexTest.purchasing_orders_report` LIMIT 10
```

Check the email — subject will be `[Plex ETL] Purchasing Orders Test — SUCCESS — DATE`.

---

## Environments: Prod vs Test

| Setting | Production | Test |
|---|---|---|
| Sales Orders job | `plex-etl` (2 AM UTC) | `plex-etl-test` (3 AM UTC) |
| Work Orders job | `plex-etl-work-orders` (4 AM UTC) | `plex-etl-work-orders-test` (5 AM UTC) |
| Plex ODBC Host | `vox.odbc.plex.com` ✅ | `vox.test.odbc.plex.com` ✅ |
| BigQuery Dataset | `PlexProd` | `PlexTest` |
| Report Config bucket | `gs://voxdatalake-report-configs/reports/` | `gs://voxdatalake-report-configs/test/` |
| Status | ✅ Live | ✅ Active — develop and validate here first |

**Always test in the test environment first.** The test jobs write to `PlexTest` — safe to run repeatedly, no impact on production data.

### Trigger jobs manually

```bash
# Sales Orders
gcloud run jobs execute plex-etl-test --region=us-central1 --project=voxdatalake --wait
gcloud run jobs execute plex-etl --region=us-central1 --project=voxdatalake --wait

# Work Orders
gcloud run jobs execute plex-etl-work-orders-test --region=us-central1 --project=voxdatalake --wait
gcloud run jobs execute plex-etl-work-orders --region=us-central1 --project=voxdatalake --wait
```

### Promote to production

After verifying results in `PlexTest`, trigger the corresponding prod job. The prod job reads from `reports/*.yaml` (not `test/*.yaml`) and writes to `PlexProd`.

---

## Email Status Levels

Every run sends an email with one of three status badges:

| Badge | Color | Meaning |
|---|---|---|
| **SUCCESS** | Green | All extractions completed, all rows written |
| **PARTIAL** | Yellow | One or more extractions failed (ODBC error, BQ write error); other extractions completed successfully — check Events and Errors sections |
| **FAILED** | Red | Job crashed before completing — ODBC connection refused, config load failed, BigQuery unreachable |

> A PARTIAL run is not a silent failure — the email lists every failed extraction in the Errors section. Any rows that did succeed are still in BigQuery. The BigQuery VIEW still runs against whatever data is available. If the VIEW was refreshed while some extractions failed, the Events list includes an explicit warning that some source tables hold stale data.

---

## Data Safety Guards

These are enforced by `main.py` (added in the 2026-07-14 code review — see [CODE_REVIEW_2026-07-14.md](CODE_REVIEW_2026-07-14.md)):

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

If incremental sync is implemented in the future, use BigQuery **query parameters** (not string interpolation) for the watermark comparison — see finding 9 in [CODE_REVIEW_2026-07-14.md](CODE_REVIEW_2026-07-14.md).

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

bq_view:                      # optional — BigQuery VIEW to create after extraction
  name: string                # VIEW name in BigQuery
  sql_file: string            # gs:// URI to a .sql file (uses {gcp_project}/{dataset})
  sql: string                 # inline SQL alternative (same placeholders)
```

---

## SendGrid Email Reports

After every run the pipeline can email an HTML summary with status, row counts per table, and any errors.

### Setup

**1. Get a SendGrid API key**
- Log in at [app.sendgrid.com](https://app.sendgrid.com) → Settings → API Keys → Create
- Name it `plex-etl`, restrict to **Mail Send** only

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

Then `terraform apply -var-file=terraform.tfvars`.

**5. Test**

```bash
gcloud run jobs execute plex-etl-test \
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
- [ ] Add entry to the report YAML, push to GCS, trigger test run
- [ ] Check BigQuery for the new table: `bq query --nouse_legacy_sql "SELECT COUNT(*) FROM \`voxdatalake.PlexTest.{table}\`"`
- [ ] Decide: full refresh or incremental? (does the view have a timestamp column?)
- [ ] If adding a new report: add Cloud Run job + scheduler to `main.tf`, run `terraform apply`
- [ ] Test the BigQuery VIEW if you added `bq_view` to the YAML
- [ ] Verify row counts and spot-check a few rows against Plex
