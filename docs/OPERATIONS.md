# Operations Guide

How to configure SendGrid email reports and how to add new Plex tables, reports, or stored procedures to the pipeline.

---

## SendGrid email reports

After every run, the pipeline can send an HTML email summary showing status, row counts, and any errors. It's off by default.

### Step 1 — Get your SendGrid API key

1. Go to [app.sendgrid.com](https://app.sendgrid.com) and log in (or create a free account)
2. Left sidebar → **Settings** → **API Keys** → **Create API Key**
3. Name it `plex-etl`, set permission to **Restricted Access** → enable **Mail Send** → Create
4. Copy the key — **you only see it once**

### Step 2 — Verify your sender email

SendGrid won't send from an unverified email address.

- Left sidebar → **Settings** → **Sender Authentication**
- Choose **Single Sender Verification** (easiest — verify one email address)
- Enter the email address you'll use as `REPORT_FROM_EMAIL`
- Click the verification link sent to that inbox

> If your company owns the sending domain (e.g. `parasolgroupinc.com`), **Domain Authentication** is stronger and removes the "via sendgrid.net" label in recipients' inboxes. Ask IT for the DNS records.

### Step 3 — Store the API key in Secret Manager

```bash
echo -n 'SG.your-actual-key-here' | \
  gcloud secrets versions add sendgrid-api-key \
  --data-file=- --project=parasoldatalake
```

> The secret container is already created by Terraform. This just adds the value.

### Step 4 — Enable reporting in terraform.tfvars

Open `terraform/terraform.tfvars` and update the SendGrid section:

```hcl
sendgrid_enabled  = "true"
report_from_email = "emilio@parasolgroupinc.com"   # must be verified in Step 2
report_to_emails  = "emilio@parasolgroupinc.com,team@parasolgroupinc.com"
report_subject    = "Plex ETL — Daily Run Report"
```

Apply the changes:

```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

### Step 5 — Test it

Run the job manually and check your inbox:

```bash
gcloud run jobs execute plex-etl \
  --region=us-central1 --project=parasoldatalake --wait
```

**Email arrives within a minute of the job completing.** If it doesn't:

1. Check job logs for `SendGrid report sent with status 202` — 202 means accepted by SendGrid
2. Check your spam folder
3. Verify the sender email was confirmed in SendGrid
4. Run `gcloud secrets versions access latest --secret=sendgrid-api-key --project=parasoldatalake` to confirm the key is stored correctly

### To disable reporting

```hcl
# terraform.tfvars
sendgrid_enabled = "false"
```
Then `terraform apply`.

---

## Adding new tables, reports, or stored procedures

### How it works

The pipeline is now fully configurable via three env vars:

| Variable | What it does | Example |
|---|---|---|
| `PLEX_VIEW` | The Plex view or stored procedure name | `Part_v_Part`, `Production_Order_v_Production_Order` |
| `PLEX_FILTER` | SQL WHERE clause (or empty for all rows) | `WHERE Part_Type = 'Raw Materials'` |
| `PLEX_DATE_COL` | Timestamp column for incremental sync (empty = full refresh) | `Modified_Date`, `Ship_Date` |

The pattern for multiple tables is: **one Cloud Run job per Plex view, all using the same Docker image.** Each job has different env vars but the same code. Like calling the same API endpoint with different query params.

### How to find the Plex view name

Plex exposes its data through named views. Naming convention: `{Module}_v_{ObjectName}`. Examples:

| What you want | Likely view name |
|---|---|
| Parts master | `Part_v_Part` |
| Production orders | `Production_Order_v_Production_Order` |
| Inventory | `Inventory_v_Container_Trace` |
| Customers | `Customer_v_Customer` |
| Shipments | `Shipment_v_Container_Trace` |

To confirm the exact name and available columns: log into Plex → go to the data or report you want → note the report/data source name → ask Plex support to confirm the ODBC view name and whether your user has read access.

For **stored procedures** — Plex also exposes stored procedures as queryable views over ODBC. They appear in the ODBC catalog the same way. Use the procedure name as `PLEX_VIEW`.

### Adding a new table — two options

---

#### Option A — New Cloud Run job via Terraform (recommended for permanent tables)

This is the right approach for syncs that will run daily in production.

**1. Add the job to `terraform/main.tf`**

Copy the existing job block and change the name and env vars. Add this after the existing `google_cloud_run_v2_job.etl` resource:

```hcl
# Example: production orders sync
resource "google_cloud_run_v2_job" "etl_production_orders" {
  name     = "plex-etl-production-orders"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env { name = "GCP_PROJECT";           value = var.gcp_project }
        env { name = "BQ_DATASET";            value = var.bq_dataset }
        env { name = "BQ_TABLE";              value = "production_orders" }
        env { name = "PLEX_HOST";             value = var.plex_host }
        env { name = "PLEX_PORT";             value = "19995" }
        env { name = "PLEX_SERVER_DATASOURCE"; value = "ReportDataSource" }
        env { name = "PLEX_ODBC_USER";        value = var.plex_odbc_user }
        env { name = "SECRET_ACCESS_TOKEN";   value = var.secret_access_token }
        env { name = "PLEX_VIEW";             value = "Production_Order_v_Production_Order" }
        env { name = "PLEX_FILTER";           value = "" }
        env { name = "PLEX_DATE_COL";         value = "Modified_Date" }
        env { name = "METADATA_TABLE";        value = var.metadata_table }
        env { name = "BACKFILL_MINUTES";      value = tostring(var.backfill_minutes) }
        env { name = "SENDGRID_ENABLED";      value = var.sendgrid_enabled }
        env { name = "REPORT_FROM_EMAIL";     value = var.report_from_email }
        env { name = "REPORT_TO_EMAILS";      value = var.report_to_emails }
        env { name = "SECRET_SENDGRID_KEY";   value = var.secret_sendgrid_key }
      }
      max_retries = 3
      timeout     = "600s"
    }
  }
}
```

**2. Add a scheduler for it (if you want it to run automatically)**

```hcl
resource "google_cloud_scheduler_job" "etl_production_orders" {
  name        = "plex-production-orders-sync"
  description = "Daily sync of Plex production orders"
  schedule    = "0 3 * * *"   # 3 AM UTC — stagger from the parts job
  time_zone   = "UTC"
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/plex-etl-production-orders:run"
    body        = base64encode("{}")
    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}
```

**3. Apply**

```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

---

#### Option B — One-off manual run (for testing a new view before committing to Terraform)

Run against any view without changing any code or infrastructure:

```bash
gcloud run jobs update plex-etl \
  --region=us-central1 \
  --project=parasoldatalake \
  --update-env-vars=PLEX_VIEW=Production_Order_v_Production_Order,PLEX_FILTER=,BQ_TABLE=production_orders_test

gcloud run jobs execute plex-etl \
  --region=us-central1 --project=parasoldatalake --wait
```

Check BigQuery for the result:
```bash
bq query --project_id=parasoldatalake --nouse_legacy_sql \
  "SELECT COUNT(*) FROM \`parasoldatalake.plex_sandbox.production_orders_test\`"
```

**Once it looks right, switch back** to the parts job and add a proper Terraform job (Option A):
```bash
gcloud run jobs update plex-etl \
  --region=us-central1 \
  --project=parasoldatalake \
  --update-env-vars=PLEX_VIEW=Part_v_Part,PLEX_FILTER=WHERE Part_Type = 'Raw Materials',BQ_TABLE=raw_materials_parts
```

---

### Full vs incremental sync — which to use

| | Full refresh | Incremental |
|---|---|---|
| **When to use** | Reference/master data (parts, customers) that changes slowly | Transaction data (orders, shipments) that grows daily |
| **How it works** | Replaces the entire table each run (`WRITE_TRUNCATE`) | Appends only new/changed rows since last run (`WRITE_APPEND`) |
| **Plex requirement** | No timestamp column needed | View must have a timestamp column (e.g. `Modified_Date`) |
| **`PLEX_DATE_COL`** | Leave empty | Set to the column name |
| **Risk** | Table empty if job fails mid-write | Duplicates if backfill window is set wrong |

**To set a view as incremental:** set `PLEX_DATE_COL` to the timestamp column name. The `sync_metadata` table automatically tracks the high-water mark between runs.

---

### Checklist for each new table

- [ ] Confirm view name and column names with Plex support
- [ ] Confirm your ODBC user has read access to the view
- [ ] Decide: full refresh or incremental? (does the view have a timestamp column?)
- [ ] Test with Option B (manual run) before committing to Terraform
- [ ] Add the Cloud Run job + scheduler to `main.tf` (Option A)
- [ ] Run `terraform apply`
- [ ] Check BigQuery for the new table after the first run
