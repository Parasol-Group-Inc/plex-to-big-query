# API & Commands Reference

> Quick lookup for every command used in this project. All multi-line commands use `\` (backslash) for line continuation — works in Git Bash and bash. In PowerShell, replace `\` with a backtick `` ` ``.
>
> **Project:** `voxdatalake` | **Region:** `us-central1` | **Example job:** `plex-etl` — one of **16** live jobs (8 report families × prod/test). Substitute any other job name in the commands below the same way.

---

## Table of contents

1. [gcloud — Auth & Project Setup](#1-gcloud--auth--project-setup)
2. [gcloud — Secret Manager](#2-gcloud--secret-manager)
3. [gcloud — Cloud Run Jobs](#3-gcloud--cloud-run-jobs)
4. [gcloud — Cloud Scheduler](#4-gcloud--cloud-scheduler)
5. [gcloud — Artifact Registry & Docker](#5-gcloud--artifact-registry--docker)
6. [gcloud — IAM & Service Accounts](#6-gcloud--iam--service-accounts)
7. [gcloud — Logging](#7-gcloud--logging)
8. [Terraform](#8-terraform)
9. [Docker](#9-docker)
10. [BigQuery (bq CLI)](#10-bigquery-bq-cli)
11. [Diagnostic quick-checks](#11-diagnostic-quick-checks)

---

## 1. gcloud — Auth & Project Setup

### Log in

```bash
# Log in with your Google account (opens browser)
gcloud auth login

# Separate login for Terraform (Application Default Credentials)
gcloud auth application-default login

# Check who you're logged in as
gcloud auth list
```

### Set default project

```bash
gcloud config set project voxdatalake

# Verify
gcloud config get-value project
```

### Check your IAM permissions on the project

```bash
gcloud projects get-iam-policy voxdatalake \
  --flatten="bindings[].members" \
  --filter="bindings.members:emilio.dominguez@parasolgroupinc.com"
```

---

## 2. gcloud — Secret Manager

### List all secrets in the project

```bash
gcloud secrets list --project=voxdatalake
```

### List versions of a specific secret

```bash
gcloud secrets versions list plex-access-token --project=voxdatalake
```

### Add a new value to a secret (rotate token)

```bash
echo -n 'YOUR_TOKEN_HERE' | \
  gcloud secrets versions add plex-access-token \
  --data-file=- --project=voxdatalake
```

> Always use `echo -n` (no trailing newline). A trailing newline becomes part of the secret value and will break authentication.

### Read a secret value (verify what's stored)

```bash
gcloud secrets versions access latest \
  --secret=plex-access-token \
  --project=voxdatalake
```

### Delete a secret (and all its versions)

```bash
gcloud secrets delete plex-access-token --project=voxdatalake --quiet
```

### Check which service accounts can access a secret

```bash
gcloud secrets get-iam-policy plex-access-token --project=voxdatalake
```

---

## 3. gcloud — Cloud Run Jobs

### Execute the job manually

```bash
# Run and wait for completion (shows exit status in terminal)
gcloud run jobs execute plex-etl \
  --region=us-central1 \
  --project=voxdatalake \
  --wait

# Run without waiting (fire and forget)
gcloud run jobs execute plex-etl \
  --region=us-central1 \
  --project=voxdatalake
```

### Describe the job (see current config and env vars)

```bash
gcloud run jobs describe plex-etl \
  --region=us-central1 \
  --project=voxdatalake
```

### Update a single environment variable

```bash
gcloud run jobs update plex-etl \
  --region=us-central1 \
  --project=voxdatalake \
  --update-env-vars=PLEX_HOST=vox.odbc.plex.com
```

> **This is a temporary/drifting change unless mirrored in `terraform.tfvars`.** Every job's `lifecycle { ignore_changes }` only covers the `image`/`client`/`client_version` fields — env vars are still fully Terraform-managed, so the next `terraform apply` will silently revert this back to whatever `terraform.tfvars` says. Use this for a quick live test only; make the durable change in `terraform.tfvars` (and re-upload its GCS backup) if you want it to stick.

### Update multiple environment variables at once

```bash
gcloud run jobs update plex-etl \
  --region=us-central1 \
  --project=voxdatalake \
  --update-env-vars=PLEX_HOST=vox.odbc.plex.com,PLEX_SERVER_DATASOURCE=ProductionDataSource
```

### Common env var overrides

| Variable | Test value | Production value |
|---|---|---|
| `REPORT_CONFIG_GCS_PATH` | `gs://voxdatalake-report-configs/test/{report}.yaml` | `gs://voxdatalake-report-configs/reports/{report}.yaml` — **the variable that actually determines which reports a job runs**; every live job sets this, the legacy `PLEX_VIEW`/`BQ_TABLE` path below is dead code unless this is empty |
| `PLEX_HOST` | `vox.test.odbc.plex.com` | `vox.odbc.plex.com` |
| `PLEX_SERVER_DATASOURCE` | `ReportDataSource` | TBD — confirm with Plex support |
| `PLEX_PORT` | `19995` | `19995` |

### List recent executions

```bash
gcloud run jobs executions list \
  --job=plex-etl \
  --region=us-central1 \
  --project=voxdatalake
```

### Describe a specific execution (get details on a run)

```bash
gcloud run jobs executions describe <execution-name> \
  --region=us-central1 \
  --project=voxdatalake
```

> Get the execution name from `executions list` above. Looks like `plex-etl-abc12`.

---

## 4. gcloud — Cloud Scheduler

### List all scheduler jobs

```bash
gcloud scheduler jobs list \
  --location=us-central1 \
  --project=voxdatalake
```

### Trigger the job immediately (same as the scheduled trigger)

```bash
gcloud scheduler jobs run plex-daily-sync \
  --location=us-central1 \
  --project=voxdatalake
```

### Pause the schedule (stops auto-runs, keeps everything deployed)

```bash
gcloud scheduler jobs pause plex-daily-sync \
  --location=us-central1 \
  --project=voxdatalake
```

> **Every job also has a separate 9:45 PM Mountain retry scheduler** (e.g. `plex-daily-sync-retry`, `RUN_MODE=retry`) that fires independently of the one above. Pausing the daily trigger does NOT pause its retry counterpart — pause both if you want a job fully quiet:
> ```bash
> gcloud scheduler jobs pause plex-daily-sync-retry --location=us-central1 --project=voxdatalake
> ```

### Resume the schedule

```bash
gcloud scheduler jobs resume plex-daily-sync \
  --location=us-central1 \
  --project=voxdatalake
```
Resume the paired `-retry` scheduler too, if you paused it.

### Change the cron schedule (easier via Terraform)

Edit `terraform/terraform.tfvars`:
```hcl
scheduler_cron = "30 19 * * *"   # 7:30 PM Mountain instead of 7:00 PM (scheduler_time_zone is now America/Denver)
```
Then:
```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

---

## 5. gcloud — Artifact Registry & Docker

### Authenticate Docker to push/pull from Artifact Registry

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
```

> Run this once per machine. Adds GCP credentials to your Docker config.

### List repositories

```bash
gcloud artifacts repositories list \
  --location=us-central1 \
  --project=voxdatalake
```

### List images in the repo

```bash
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/voxdatalake/plex-pipeline \
  --project=voxdatalake
```

### Delete an old image (cleanup)

```bash
gcloud artifacts docker images delete \
  us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:old-tag \
  --project=voxdatalake --quiet
```

---

## 6. gcloud — IAM & Service Accounts

### List service accounts

```bash
gcloud iam service-accounts list --project=voxdatalake
```

### Check what roles a service account has

```bash
gcloud projects get-iam-policy voxdatalake \
  --flatten="bindings[].members" \
  --filter="bindings.members:plex-etl-sa@voxdatalake.iam.gserviceaccount.com"
```

### Grant a role to your own account (requires Owner)

```bash
gcloud projects add-iam-policy-binding voxdatalake \
  --member="user:emilio.dominguez@parasolgroupinc.com" \
  --role="roles/owner"
```

---

## 7. gcloud — Logging

### Stream logs live while a job is running

```bash
gcloud beta run jobs executions tail-logs <execution-name> \
  --region=us-central1 \
  --project=voxdatalake
```

### Read recent logs from the plex-etl job

```bash
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl" \
  --project=voxdatalake \
  --limit=50 \
  --format="table(timestamp,textPayload)"
```

### Filter logs to errors only

```bash
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl AND severity>=ERROR" \
  --project=voxdatalake \
  --limit=20 \
  --format="table(timestamp,textPayload)"
```

### Logs for a specific execution

```bash
gcloud logging read \
  "resource.type=cloud_run_job AND labels.\"run.googleapis.com/execution_name\"=plex-etl-abc12" \
  --project=voxdatalake \
  --limit=100 \
  --format="table(timestamp,textPayload)"
```

### GCP Console path for logs

Console → **Cloud Run** → **Jobs** → `plex-etl` → click any execution → **Logs** tab. Usually easier to read than CLI output.

---

## 8. Terraform

All Terraform commands must be run from the `terraform/` directory.

```bash
cd terraform
```

### Initialize (first time or after editing provider config)

```bash
terraform init
```

### Preview what will change (dry run)

```bash
terraform plan -var-file=terraform.tfvars
```

### Apply changes

```bash
terraform apply -var-file=terraform.tfvars
```

After any edit to `terraform.tfvars` itself (not just after applying it), back it up — it's gitignored and only ever exists on your machine:
```bash
gcloud storage cp terraform.tfvars gs://voxdatalake-terraform-state/plex-to-big-query/terraform.tfvars.backup
```

### List all resources in state

```bash
terraform state list
```

### Show details of a specific resource in state

```bash
terraform state show google_cloud_run_v2_job.etl
```

### Import an existing GCP resource into state

Use when `terraform apply` fails with 409 "Already Exists" — the resource exists in GCP but not in your state file.

```bash
# Secrets
terraform import google_secret_manager_secret.access_token \
  projects/voxdatalake/secrets/plex-access-token

terraform import google_secret_manager_secret.odbc_user \
  projects/voxdatalake/secrets/plex-odbc-user

terraform import google_secret_manager_secret.odbc_password \
  projects/voxdatalake/secrets/plex-odbc-password

terraform import google_secret_manager_secret.company_code \
  projects/voxdatalake/secrets/plex-company-code

# BigQuery datasets — .plex is PROD (PlexProd), .plex_test is TEST (PlexTest).
# Importing PlexTest into .plex (as an earlier version of this doc showed)
# imports the wrong dataset into the wrong resource address and will fail
# or corrupt state — match the resource to the right dataset:
terraform import google_bigquery_dataset.plex voxdatalake/PlexProd
terraform import google_bigquery_dataset.plex_test voxdatalake/PlexTest

# Service account
terraform import google_service_account.etl \
  projects/voxdatalake/serviceAccounts/plex-etl-sa@voxdatalake.iam.gserviceaccount.com

# Artifact Registry repo
terraform import google_artifact_registry_repository.etl \
  projects/voxdatalake/locations/us-central1/repositories/plex-pipeline
```

### Remove a resource from state (without deleting it from GCP)

```bash
terraform state rm google_cloud_run_v2_job.etl
```

### Wipe all state (nuclear option — only if state is hopelessly corrupted)

State lives in `gs://voxdatalake-terraform-state/plex-to-big-query/default.tfstate` (GCS backend, versioning enabled) — not a local file. Try rolling back to a previous object version first (`gcloud storage ls -a gs://voxdatalake-terraform-state/plex-to-big-query/default.tfstate`) before wiping outright:

```bash
gcloud storage rm gs://voxdatalake-terraform-state/plex-to-big-query/default.tfstate
terraform init
# Then re-import everything above, then apply
```

### Show Terraform outputs (handy commands after apply)

```bash
terraform output
```

---

## 9. Docker

> **Building and pushing an image is not a complete deploy by itself.** Every `google_cloud_run_v2_job` has `lifecycle { ignore_changes = [image, ...] }` — no job ever auto-picks up a new image, not per-execution and not via `terraform apply`. After pushing, you must explicitly redeploy (see the last command below), or use `deploy/cloudbuild.yaml`'s `deploy-all` step, which does this for all 16 jobs from one build.

### Build the image

```bash
# From repo root (not terraform/). Tag with the commit SHA — never ":latest"
# for anything that gets deployed; ":latest" is still built for convenience/
# manual `docker pull` only.
SHA=$(git rev-parse --short HEAD)
docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA \
             -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest .
```

### Push to Artifact Registry

```bash
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest
```

### Build, push, and redeploy in one go

```bash
SHA=$(git rev-parse --short HEAD)
docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA \
             -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest . && \
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA && \
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest && \
gcloud run jobs update plex-etl --image=us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA --region=us-central1
```
Repeat the last `gcloud run jobs update` per job, or loop over all 16 (see `docs/TROUBLESHOOTING.md` § "Full rebuild procedure" for the full loop), or just run `gcloud builds submit --config deploy/cloudbuild.yaml` instead — it does all of this in one call.

### Run locally (Phase 1 — writes CSVs to ./output/)

```bash
docker compose up

# Rebuild first if code/config changed
docker compose build && docker compose up
```

### Run with a different env var (override for testing)

```bash
docker compose run --rm etl \
  -e PLEX_HOST=vox.test.odbc.plex.com
```

### Check what's inside the built image (debugging)

```bash
docker run --rm -it \
  us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest \
  /bin/bash
```

### List local images

```bash
docker images | grep plex
```

### Clean up old images

```bash
docker image prune -f
```

---

## 10. BigQuery (bq CLI)

### Count rows in the parts table

```bash
bq query --project_id=voxdatalake --nouse_legacy_sql \
  "SELECT COUNT(*) AS part_count FROM \`voxdatalake.PlexTest.raw_Part_v_Part\`"
```

### Preview the parts table

```bash
bq query --project_id=voxdatalake --nouse_legacy_sql \
  "SELECT Part_No, Name, Part_Status FROM \`voxdatalake.PlexTest.raw_Part_v_Part\` LIMIT 10"
```

### Check recent sync metadata

```bash
bq query --project_id=voxdatalake --nouse_legacy_sql \
  "SELECT * FROM \`voxdatalake.PlexTest.sync_metadata\` ORDER BY synced_at DESC LIMIT 5"
```

### List tables in the dataset

```bash
bq ls voxdatalake:PlexTest
```

### Show a table's schema

```bash
bq show voxdatalake:PlexTest.raw_Part_v_Part
```

### GCP Console path

Console → **BigQuery** → `voxdatalake` → `PlexTest` → click any table → **Preview** tab for data, **Schema** tab for columns.

---

## 11. Diagnostic quick-checks

Use these when something seems wrong.

### Is the Plex token stored?

```bash
gcloud secrets versions list plex-access-token --project=voxdatalake
# Expect: at least one version with state "enabled"
```

### What env vars does Cloud Run have?

```bash
gcloud run jobs describe plex-etl --region=us-central1 --project=voxdatalake
# Look for the "Env vars:" section near the bottom
```

### Did the last job run succeed?

```bash
gcloud run jobs executions list \
  --job=plex-etl --region=us-central1 --project=voxdatalake \
  --limit=5
# Look at COMPLETION_STATUS column — EXECUTION_SUCCEEDED or EXECUTION_FAILED
```

### What's actually in BigQuery right now?

```bash
bq query --project_id=voxdatalake --nouse_legacy_sql \
  "SELECT COUNT(*) FROM \`voxdatalake.PlexTest.raw_Part_v_Part\`"
```

### Is the scheduler enabled?

```bash
gcloud scheduler jobs describe plex-daily-sync \
  --location=us-central1 --project=voxdatalake
# Look for "state: ENABLED" or "state: PAUSED"
```

### Full health check — run all at once

```bash
echo "=== Token ===" && \
gcloud secrets versions list plex-access-token --project=voxdatalake && \
echo "=== Last 3 executions ===" && \
gcloud run jobs executions list --job=plex-etl --region=us-central1 --project=voxdatalake --limit=3 && \
echo "=== Scheduler state ===" && \
gcloud scheduler jobs describe plex-daily-sync --location=us-central1 --project=voxdatalake --format="value(state)"
```
