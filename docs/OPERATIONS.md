# Operations Guide

Day-to-day operations: editing reports, adding new reports, configuring SendGrid, and managing environments.

---

## How the Report System Works

Reports are defined by **YAML files stored in Cloud Storage** — not hardcoded in the container image or Terraform variables. This means you can change what gets extracted and how the BigQuery view looks without any code deployment.

```
gs://voxdatalake-report-configs/
├── reports/
│   ├── sales_orders.yaml          ← prod: 13 Plex views → PlexProd
│   └── (future reports here)
├── test/
│   └── sales_orders.yaml          ← test: same views → PlexTest
└── sql/
    └── sales_orders_view.sql      ← BigQuery JOIN view SQL ✏ edit here
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
gsutil cp reports/sales_orders.yaml gs://voxdatalake-report-configs/reports/
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
gsutil cp reports/sql/sales_orders_view.sql \
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

### Step 1 — Create the YAML

```bash
cp reports/sales_orders.yaml reports/purchasing_orders.yaml
```

Edit `reports/purchasing_orders.yaml`:

```yaml
report_name: purchasing_orders
description: "Daily purchasing orders from Plex Purchasing module"

extractions:
  - plex_view: Purchasing_v_PO
    bq_table: raw_Purchasing_v_PO
    filter: ""
    date_col: ""

  - plex_view: Purchasing_v_PO_Line
    bq_table: raw_Purchasing_v_PO_Line
    filter: ""
    date_col: ""

# Optional: define a BigQuery VIEW that JOINs the raw tables
bq_view:
  name: purchasing_orders_report
  sql_file: gs://voxdatalake-report-configs/sql/purchasing_orders_view.sql
```

### Step 2 — Create the SQL (optional)

```bash
cp reports/sql/sales_orders_view.sql reports/sql/purchasing_orders_view.sql
# Edit to match your join logic
```

### Step 3 — Push to GCS

```bash
gsutil cp reports/purchasing_orders.yaml \
  gs://voxdatalake-report-configs/reports/

gsutil cp reports/sql/purchasing_orders_view.sql \
  gs://voxdatalake-report-configs/sql/
```

### Step 4 — Add a Cloud Run Job in `terraform/main.tf`

Copy the existing `google_cloud_run_v2_job.etl` block. Change the job name and `REPORT_CONFIG_GCS_PATH`:

```hcl
resource "google_cloud_run_v2_job" "etl_purchasing" {
  name     = "plex-etl-purchasing"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env { name = "GCP_PROJECT";            value = var.gcp_project }
        env { name = "BQ_DATASET";             value = var.bq_dataset }
        env { name = "BQ_TABLE";               value = "purchasing_orders" }
        env { name = "PLEX_HOST";              value = var.plex_host }
        env { name = "PLEX_PORT";              value = "19995" }
        env { name = "PLEX_SERVER_DATASOURCE"; value = "ReportDataSource" }
        env { name = "PLEX_ODBC_USER";         value = var.plex_odbc_user }
        env { name = "SECRET_ACCESS_TOKEN";    value = var.secret_access_token }
        # ↓ This is the only thing that differs per report
        env { name = "REPORT_CONFIG_GCS_PATH"; value = "gs://voxdatalake-report-configs/reports/purchasing_orders.yaml" }
        env { name = "METADATA_TABLE";         value = var.metadata_table }
        env { name = "BACKFILL_MINUTES";       value = tostring(var.backfill_minutes) }
        env { name = "SENDGRID_ENABLED";       value = var.sendgrid_enabled }
        env { name = "REPORT_FROM_EMAIL";      value = var.report_from_email }
        env { name = "REPORT_TO_EMAILS";       value = var.report_to_emails }
        env { name = "SECRET_SENDGRID_KEY";    value = var.secret_sendgrid_key }
        env { name = "COMPANY_NAME";           value = var.company_name }
      }
      max_retries = 3
      timeout     = "600s"
    }
  }
}

resource "google_cloud_scheduler_job" "etl_purchasing" {
  name      = "plex-purchasing-sync"
  schedule  = "0 4 * * *"
  time_zone = "UTC"
  region    = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/plex-etl-purchasing:run"
    body        = base64encode("{}")
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}
```

### Step 5 — Apply Terraform

```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

---

## Environments: Prod vs Test

| Setting | Production | Test |
|---|---|---|
| Cloud Run Job | `plex-etl` | `plex-etl-test` |
| Cloud Scheduler | `plex-daily-sync` (2 AM UTC) | `plex-daily-sync-test` (3 AM UTC) |
| Plex ODBC Host | `odbc.plex.com` ⚠ pending | `vox.odbc.plex.com` ✅ |
| BigQuery Dataset | `PlexProd` | `PlexTest` |
| Report Config | `gs://.../reports/sales_orders.yaml` | `gs://.../test/sales_orders.yaml` |
| Status | Blocked — prod ServerDataSource TBD | Active — use for all development |

**Always test in the test environment first.** The `plex-etl-test` job writes to `PlexTest` — safe to run repeatedly, no impact on production data.

### Trigger test job manually

```bash
gcloud run jobs execute plex-etl-test \
  --region=us-central1 --project=voxdatalake --wait
```

### Promote to production

After verifying results in `PlexTest`:
1. Confirm the prod report YAML is correct (`reports/sales_orders.yaml`)
2. Get Plex support to confirm `ServerDataSource` for `odbc.plex.com`
3. Run the production job:

```bash
gcloud run jobs execute plex-etl \
  --region=us-central1 --project=voxdatalake --wait
```

---

## Full vs Incremental Sync

| | Full refresh | Incremental |
|---|---|---|
| **When to use** | Reference/master data (parts, customers, lookups) | Transaction data (orders, releases, shipments) that grows daily |
| **How it works** | Replaces the entire table each run (`WRITE_TRUNCATE`) | Appends only new/changed rows since last run |
| **Plex requirement** | No timestamp column needed | View must have a timestamp column (e.g. `Change_Date`) |
| **`date_col` in YAML** | Leave empty `""` | Set to the column name |
| **Current approach** | All 13 views in the sales orders report | `Sales_v_PO_Change` uses `Change_Date` |

To switch a view to incremental, set `date_col` to the timestamp column name in the YAML and push to GCS:

```yaml
  - plex_view: Sales_v_PO_Change
    bq_table: raw_Sales_v_PO_Change
    filter: ""
    date_col: Change_Date    # ← enables incremental sync
```

---

## YAML Schema Reference

```yaml
report_name: string           # required — identifier for logs and email reports
description: string           # optional — human-readable description

extractions:                  # required — list of Plex views to extract
  - plex_view: string         # required — Plex ODBC view name ({DB}_v_{View})
    bq_table: string          # required — destination BigQuery table name
    filter: string            # optional — SQL WHERE clause, e.g. "WHERE Active = 1"
    date_col: string          # optional — column for incremental sync watermark

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
