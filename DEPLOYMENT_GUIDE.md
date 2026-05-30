# GCP Deployment Guide — Phase 2

## What this gets you

By the end of this guide:

- All GCP infrastructure provisioned by Terraform
- Docker image built and pushed to Artifact Registry
- Plex IAM token stored in Secret Manager
- Cloud Run job executing successfully against Plex and writing to BigQuery
- Cloud Scheduler running on a daily cron schedule

---

## Prerequisites checklist

- [ ] **Phase 1 complete** — `docker compose up` ran locally and produced a CSV in `./output/`
- [ ] **GCP project** created (`vox-nutrition-prod`) with billing enabled
- [ ] **`gcloud` CLI** installed and authenticated
  ```powershell
  gcloud version
  gcloud auth login
  gcloud auth application-default login
  ```
- [ ] **Terraform** >= 1.5.0 installed
  ```powershell
  terraform version
  ```
- [ ] **Docker** running (same Docker Desktop from Phase 1)
- [ ] `driver/` folder populated (same as Phase 1)

---

## Step 1 — Update `main.py` for BigQuery full-refresh mode

The `Part_v_Part` data source is a full refresh (no date column). Before deploying, update `write_to_bigquery()` to use `WRITE_TRUNCATE` instead of `WRITE_APPEND` and define an explicit schema:

In [main.py](main.py), find `write_to_bigquery()` and replace the `LoadJobConfig`:

```python
job_config = bigquery.LoadJobConfig(
    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
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

> For future incremental tables (with a date column), keep `WRITE_APPEND` and the schema for that view.

---

## Step 2 — Terraform setup

### 2.1 Create `terraform.tfvars`

```powershell
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Fill in `terraform.tfvars`:

```hcl
gcp_project    = "vox-nutrition-prod"
bq_dataset     = "plex_dataset"
bq_table       = "raw_materials_parts"
plex_host      = "odbc.plex.com"          # production Plex ODBC host
plex_odbc_user = "edominguez.parasol"     # Plex login (username.company)
image_url      = "us-central1-docker.pkg.dev/vox-nutrition-prod/plex-pipeline/etl:latest"
```

Leave `image_url` as the correct format even before the image is pushed — Terraform will create the Cloud Run job definition and you will push the image in Step 4.

### 2.2 Initialize and apply

```powershell
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

Type `yes` when prompted. Takes 2–5 minutes (API enablement is slowest).

> **If apply fails "API not yet enabled":** Wait 60 seconds and re-run. GCP API enablement is eventually consistent.

### 2.3 Store the IAM token in Secret Manager

Terraform creates the secret container but does not populate it. Add the token value:

```powershell
# Replace <token> with the value from PLEX_ACCESS_TOKEN in your .env
echo -n 'Mjc4MDIyN2Et...' | gcloud secrets versions add plex-access-token `
  --data-file=- --project=vox-nutrition-prod
```

Verify:
```powershell
gcloud secrets versions list plex-access-token --project=vox-nutrition-prod
# Should show: VERSION  STATE    CREATED
#              1        enabled  ...
```

> **Token rotation:** Plex IAM tokens are long-lived but will eventually need refreshing. When you get a new token from Plex, add it as a new version — Cloud Run automatically picks up `latest`:
> ```powershell
> echo -n 'NEW_TOKEN' | gcloud secrets versions add plex-access-token --data-file=- --project=vox-nutrition-prod
> ```

---

## Step 3 — Update `main.py` Secret Manager retrieval

In [main.py](main.py), the IAM auth branch currently reads `PLEX_ACCESS_TOKEN` directly from the environment. For Cloud Run, it must fall back to Secret Manager. Verify this block in `main()`:

```python
access_token = os.environ.get("PLEX_ACCESS_TOKEN", "")
if not access_token and OUTPUT_MODE == "bigquery":
    try:
        access_token = get_secret(SECRET_TOKEN)
    except Exception:
        pass  # fall through to username/password auth
```

`SECRET_TOKEN` defaults to `"plex-access-token"` which matches the secret created in Step 2.3. No code change needed — this was already wired in.

---

## Step 4 — Build and push the Docker image

Run from the **repo root**:

```powershell
# Authenticate Docker to Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build (replace project ID and region if different)
docker build -t us-central1-docker.pkg.dev/vox-nutrition-prod/plex-pipeline/etl:latest .

# Push
docker push us-central1-docker.pkg.dev/vox-nutrition-prod/plex-pipeline/etl:latest
```

Then re-apply Terraform so the Cloud Run job picks up the real image:

```powershell
cd terraform
terraform apply -var-file=terraform.tfvars
```

---

## Step 5 — Test the Cloud Run job manually

```powershell
gcloud run jobs execute plex-etl `
  --region=us-central1 `
  --project=vox-nutrition-prod `
  --wait
```

Check the logs:
```powershell
gcloud logging read `
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl" `
  --project=vox-nutrition-prod `
  --limit=50 `
  --format="table(timestamp,textPayload)"
```

Expected success log sequence:
```
[INFO] Fetching credentials...
[INFO] Using IAM access token for Plex authentication.
[INFO] Connecting driver-direct to odbc.plex.com:19995 (IAM token auth, UID=edominguez.parasol)
[INFO] ODBC connection established.
[INFO] Querying Plex [Part_v_Part] for Raw Materials parts...
[INFO] Fetched NNN Raw Materials parts from Plex.
[INFO] Writing NNN rows to vox-nutrition-prod.plex_dataset.raw_materials_parts...
[INFO] === ETL job complete — NNN rows written ===
```

---

## Step 6 — Verify data in BigQuery

```powershell
bq query --project_id=vox-nutrition-prod --nouse_legacy_sql `
  "SELECT COUNT(*) AS part_count FROM \`vox-nutrition-prod.plex_dataset.raw_materials_parts\`"

bq query --project_id=vox-nutrition-prod --nouse_legacy_sql `
  "SELECT Part_No, Name, Part_Status FROM \`vox-nutrition-prod.plex_dataset.raw_materials_parts\` LIMIT 10"
```

---

## Step 7 — Verify Cloud Scheduler

Terraform creates a scheduler job at `0 2 * * *` (2 AM UTC daily):

```powershell
gcloud scheduler jobs list --location=us-central1 --project=vox-nutrition-prod
```

Trigger it immediately to confirm end-to-end:
```powershell
gcloud scheduler jobs run plex-daily-sync --location=us-central1 --project=vox-nutrition-prod
```

---

## Step 8 — CI/CD with Cloud Build (optional)

`deploy/cloudbuild.yaml` automates build → push → deploy on every push to `main`.

1. Store the driver in GCS (avoids committing binaries):
   ```powershell
   gcloud storage buckets create gs://vox-nutrition-prod-build-assets --project=vox-nutrition-prod
   gcloud storage cp -r driver/* gs://vox-nutrition-prod-build-assets/plex-odbc-driver/
   ```

2. Create a Cloud Build trigger in GCP Console:
   - Source: this repo
   - Branch: `main`
   - Config: `deploy/cloudbuild.yaml`

---

## Troubleshooting

### Cloud Run job: `Secret not found` or `Permission denied on secret`

Verify the secret has a version (Step 2.3) and the service account has `roles/secretmanager.secretAccessor`:
```powershell
gcloud projects get-iam-policy vox-nutrition-prod `
  --flatten="bindings[].members" `
  --filter="bindings.members:plex-etl-sa@"
```

### Cloud Run job: ODBC connection error

- Confirm `PLEX_HOST` in `terraform.tfvars` is the correct production Plex ODBC endpoint
- If Plex restricts by IP: Cloud Run uses variable egress IPs. Add a VPC connector + Cloud NAT for a fixed outbound IP, then allowlist it with Plex.

### Cloud Run job: `WRITE_TRUNCATE` wipes the table on error

If the job fails mid-write, the table may be empty on the next query. This is acceptable for a full-refresh table — the next successful run restores it. To avoid this window, load into a staging table first and swap with `CREATE OR REPLACE TABLE ... AS SELECT`.

### Terraform: `image not found / manifest unknown`

Push the Docker image (Step 4) before re-applying Terraform.

---

## Operational runbook

**Rotate the IAM token:**
```powershell
echo -n 'NEW_TOKEN' | gcloud secrets versions add plex-access-token --data-file=- --project=vox-nutrition-prod
```

**Change the sync schedule:**
Update `scheduler_cron` in `terraform.tfvars`, then `terraform apply`.

**Pause the pipeline:**
```powershell
gcloud scheduler jobs pause plex-daily-sync --location=us-central1 --project=vox-nutrition-prod
```

**Resume the pipeline:**
```powershell
gcloud scheduler jobs resume plex-daily-sync --location=us-central1 --project=vox-nutrition-prod
```

**View recent job history:**
```powershell
gcloud run jobs executions list --job=plex-etl --region=us-central1 --project=vox-nutrition-prod
```

**Add a second Plex table:**
1. Add a new `query_plex()` variant (or make the view configurable via env var)
2. Update `BQ_TABLE` in the Cloud Run job env, or run a second Cloud Run job for the second table
3. Define the BigQuery schema for the new table
