# GCP Deployment Guide — Phase 2

## What this gets you

By the end of this guide:

- All GCP infrastructure provisioned by Terraform (service account, BigQuery dataset, Secret Manager secrets, Artifact Registry, Cloud Run job, Cloud Scheduler)
- Docker image built and pushed to Artifact Registry
- Plex credentials stored in Secret Manager
- Cloud Run job executing successfully against real Plex and writing to BigQuery
- Cloud Scheduler running on a daily cron schedule

---

## Prerequisites checklist

- [ ] **Phase 1 complete** — you have run `docker compose up` locally and verified the CSV output looks correct
- [ ] **GCP project** created with billing enabled
- [ ] **`gcloud` CLI** installed and authenticated
  ```powershell
  gcloud version        # verify install
  gcloud auth login     # authenticate
  gcloud auth application-default login   # authenticate for Terraform
  ```
- [ ] **Terraform** >= 1.5.0 installed
  ```powershell
  terraform version
  ```
- [ ] **Docker** running (same Docker Desktop from Phase 1)
- [ ] `driver/` folder populated (same as Phase 1)

---

## Section 1 — Terraform setup

### 1.1 Create your `terraform.tfvars` file

```powershell
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and fill in every value. The most important fields:

```hcl
gcp_project = "your-actual-project-id"   # required, no default
bq_table    = "production_orders"         # must match your SQL query
image_url   = "us-central1-docker.pkg.dev/your-project/plex-pipeline/etl:latest"
```

> **Note on `image_url`:** Artifact Registry does not exist yet, so this URL cannot be valid on your first apply. Set it to the correct format (`REGION-docker.pkg.dev/PROJECT/REPO/IMAGE:TAG`) even if the image hasn't been pushed yet. Terraform will create the Cloud Run job with this URL — you will push the image and re-apply in Section 2.

### 1.2 Initialize Terraform

```powershell
terraform init
```

Expected output: `Terraform has been successfully initialized!`

This downloads the Google provider plugin. It only needs to run once (or after adding new providers).

### 1.3 Preview what will be created

```powershell
terraform plan -var-file=terraform.tfvars
```

Review the output. Confirm you see resources for:
- `google_project_service` (API enablement)
- `google_service_account`
- `google_bigquery_dataset` and `google_bigquery_table`
- `google_artifact_registry_repository`
- `google_secret_manager_secret` (×3)
- `google_cloud_run_v2_job`
- `google_cloud_scheduler_job`

Nothing is created until you run apply.

### 1.4 Apply Terraform

```powershell
terraform apply -var-file=terraform.tfvars
```

Type `yes` when prompted. The apply takes 2–5 minutes (API enablement is the slowest step).

Expected ending:
```
Apply complete! Resources: 18 added, 0 changed, 0 destroyed.

Outputs:
...
```

**Copy the full outputs section** — you will use the commands in the next steps.

> **If apply fails with "API not yet enabled":** Wait 60 seconds and run `terraform apply` again. GCP API enablement is eventually consistent.

### 1.5 Add secret versions (mandatory)

Terraform creates the Secret Manager secret containers but does NOT populate them with values. You must add the actual credentials now.

Use the `secret_version_commands` output from Step 1.4. It looks like this (replace the placeholder values):

```powershell
echo -n 'YOUR_PLEX_USER'     | gcloud secrets versions add plex-odbc-user     --data-file=- --project=your-project
echo -n 'YOUR_PLEX_PASSWORD' | gcloud secrets versions add plex-odbc-password --data-file=- --project=your-project
echo -n 'YOUR_COMPANY_CODE'  | gcloud secrets versions add plex-company-code  --data-file=- --project=your-project
```

Verify the secrets have versions:

```powershell
gcloud secrets versions list plex-odbc-user --project=your-project
# Should show: VERSION  STATE    CREATED
#              1        enabled  ...
```

---

## Section 2 — Build and push the Docker image

Run all commands from the **repo root** (not inside `terraform/`).

### 2.1 Authenticate Docker to Artifact Registry

```powershell
gcloud auth configure-docker us-central1-docker.pkg.dev
```

Replace `us-central1` with your `gcp_region` if different.

### 2.2 Build the image

Use the `image_push_commands` output from Terraform, or construct it manually:

```powershell
docker build -t us-central1-docker.pkg.dev/your-project/plex-pipeline/etl:latest .
```

This build uses your local `driver/` folder and produces a Linux/amd64 image.

> **On Apple Silicon (M1/M2):** Add `--platform linux/amd64` to the build command — Cloud Run requires amd64.
> ```powershell
> docker build --platform linux/amd64 -t us-central1-docker.pkg.dev/your-project/plex-pipeline/etl:latest .
> ```

### 2.3 Push the image

```powershell
docker push us-central1-docker.pkg.dev/your-project/plex-pipeline/etl:latest
```

### 2.4 Re-apply Terraform

If you used a placeholder `image_url` in Step 1.1, update `terraform.tfvars` with the real URL you just pushed, then re-apply:

```powershell
cd terraform
terraform apply -var-file=terraform.tfvars
```

This updates the Cloud Run job definition with the correct image. Only the Cloud Run job resource changes.

---

## Section 3 — Test the Cloud Run job

### 3.1 Trigger a manual execution

Use the `cloud_run_execute_command` output from Terraform:

```powershell
gcloud run jobs execute plex-etl --region=us-central1 --project=your-project --wait
```

`--wait` blocks until the job completes and reports success or failure.

### 3.2 Check the logs

```powershell
gcloud logging read `
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl" `
  --project=your-project `
  --limit=50 `
  --format="table(timestamp,textPayload)"
```

Look for:
```
[INFO] Fetching credentials from Secret Manager...
[INFO] Connecting to Plex via DSN: PlexProduction
[INFO] ODBC connection established.
[INFO] Fetched NNN rows from Plex.
[INFO] Successfully wrote NNN rows to BigQuery.
[INFO] === ETL job complete — NNN rows written ===
```

### 3.3 Verify data in BigQuery

```powershell
# Row count in the target table
bq query --project_id=your-project --nouse_legacy_sql `
  "SELECT COUNT(*) AS row_count FROM \`your-project.plex_dataset.production_orders\`"

# Check the sync metadata
bq query --project_id=your-project --nouse_legacy_sql `
  "SELECT * FROM \`your-project.plex_dataset.sync_metadata\` ORDER BY synced_at DESC LIMIT 5"
```

---

## Section 4 — Verify Cloud Scheduler

Terraform created a scheduler job at `0 2 * * *` (2 AM UTC daily) by default. Verify:

```powershell
gcloud scheduler jobs list --location=us-central1 --project=your-project
```

To trigger the scheduler immediately (without waiting for the cron time):

```powershell
gcloud scheduler jobs run plex-daily-sync --location=us-central1 --project=your-project
```

---

## Section 5 — Email reporting (optional)

To receive a run summary email via SendGrid after each execution:

1. Get a SendGrid API key from https://app.sendgrid.com/settings/api_keys
2. Update the Cloud Run job environment variables. The easiest way is to add them to `terraform/main.tf` inside the `containers {}` block:

```hcl
env {
  name  = "SENDGRID_ENABLED"
  value = "true"
}
env {
  name  = "SENDGRID_API_KEY"
  value = "your-sendgrid-api-key"  # better: store in Secret Manager
}
env {
  name  = "REPORT_FROM_EMAIL"
  value = "etl-reports@yourcompany.com"
}
env {
  name  = "REPORT_TO_EMAILS"
  value = "analyst@yourcompany.com,ops@yourcompany.com"
}
```

Then run `terraform apply -var-file=terraform.tfvars` to update the job.

> **Security note:** Prefer storing the SendGrid API key in Secret Manager rather than as a plain env var. Add a fourth secret in Terraform and reference it via the Secret Manager accessor the same way Plex credentials are handled.

---

## Section 6 — CI/CD with Cloud Build (optional)

`deploy/cloudbuild.yaml` automates the image build, push, and Cloud Run update on every push to `main`. To activate it:

1. Create a Cloud Storage bucket for the driver files:
   ```powershell
   gcloud storage buckets create gs://your-project-build-assets --project=your-project
   ```

2. Upload the Plex ODBC driver to GCS:
   ```powershell
   gcloud storage cp -r driver/* gs://your-project-build-assets/plex-odbc-driver/
   ```

3. Create a Cloud Build trigger in the GCP Console:
   - Source: your repo
   - Branch: `main`
   - Config: `deploy/cloudbuild.yaml`

Each push to `main` will then build and deploy automatically. The build pulls the driver from GCS so the `driver/` folder does not need to be committed.

---

## Troubleshooting

### `terraform apply` fails: required APIs not enabled

GCP API enablement is eventually consistent. Wait 30–60 seconds and re-run `terraform apply`.

### Cloud Run job fails: `Secret not found` or `Permission denied on secret`

- Verify you completed Step 1.5 — secrets need a version before they can be read
- Verify the service account has `roles/secretmanager.secretAccessor`:
  ```powershell
  gcloud projects get-iam-policy your-project `
    --flatten="bindings[].members" `
    --filter="bindings.members:plex-etl-sa@"
  ```

### Cloud Run job fails: image not found / manifest unknown

- Verify the `image_url` in `terraform.tfvars` exactly matches what was pushed in Step 2.3
- Re-apply Terraform after pushing the image

### Cloud Run job fails: ODBC connection error

- Confirm the `Host` and `Port` in `config/odbc.ini` are correct
- If Plex restricts by source IP: add a VPC connector and Cloud NAT to give the Cloud Run job a fixed egress IP, then have Plex allowlist that IP

### `terraform apply` fails: `scheduler_token_creator` binding error

The Cloud Scheduler service agent is created when the API is enabled, but there can be a propagation delay. Run `terraform apply` again after 60 seconds.

---

## Operational runbook

**Rotate Plex credentials:**
```powershell
echo -n 'NEW_PASSWORD' | gcloud secrets versions add plex-odbc-password --data-file=- --project=your-project
# Cloud Run automatically picks up the :latest version on next execution
```

**Change the sync schedule:**
Update `scheduler_cron` in `terraform.tfvars` and run `terraform apply`.

**Change the target BigQuery table:**
Update `bq_table` in `terraform.tfvars` and run `terraform apply`. Note: the old table is not deleted.

**Pause the pipeline:**
```powershell
gcloud scheduler jobs pause plex-daily-sync --location=us-central1 --project=your-project
```

**Resume the pipeline:**
```powershell
gcloud scheduler jobs resume plex-daily-sync --location=us-central1 --project=your-project
```

**View recent job history:**
```powershell
gcloud run jobs executions list --job=plex-etl --region=us-central1 --project=your-project
```
