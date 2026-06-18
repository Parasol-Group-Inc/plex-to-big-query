# GCP Deployment Guide — Phase 2

## What this gets you

By the end of this guide:

- All GCP infrastructure provisioned by Terraform
- Docker image built and pushed to Artifact Registry
- Plex IAM token stored in Secret Manager
- Cloud Run job executing successfully against Plex and writing to BigQuery
- Cloud Scheduler running on a daily cron schedule

---

## How the GCP pieces fit together

If you're coming from frontend, here's a mental model for each service this pipeline uses:

| GCP Service | Think of it like… | What it does here |
|---|---|---|
| **Artifact Registry** | npm registry / Docker Hub | Stores your built Docker image |
| **Cloud Run Job** | Vercel/Lambda serverless function | Runs the ETL container on demand |
| **Cloud Scheduler** | `cron` / GitHub Actions schedule | Triggers the Cloud Run job daily at 2 AM UTC |
| **BigQuery** | Postgres / Supabase (analytics-focused, read-heavy) | Stores the extracted Plex data as queryable tables |
| **Secret Manager** | `.env` file, but encrypted + access-controlled | Holds the Plex IAM token and ODBC credentials |
| **Service Account** | API key your app authenticates with | What Cloud Run uses to talk to BigQuery, Secret Manager, etc. |
| **Terraform** | `npm install` for cloud infra | Provisions all of the above with a single `terraform apply` |

> **Two kinds of tokens:** There are two separate authentication systems at play. The **Plex IAM token** (`plex-access-token`) is how the ETL script authenticates to the Plex ERP ODBC endpoint — you store this in Secret Manager. The **GCP service account** is how Cloud Run authenticates to GCP services (BigQuery, Secret Manager) — Terraform creates this automatically. You never see the service account token directly.

---

## Prerequisites checklist

- [ ] **Phase 1 complete** — `docker compose up` ran locally and produced a CSV in `./output/`
- [ ] **GCP project** created with billing enabled
  - In GCP Console: top-left dropdown → **New Project** → note the **Project ID** (like `vox-nutrition-prod`) — this is different from the display name
  - Billing: GCP Console → **Billing** → link a billing account to the project
- [ ] **`gcloud` CLI** installed and authenticated
  ```powershell
  # Install: https://cloud.google.com/sdk/docs/install (Windows installer)
  gcloud version          # verify install
  gcloud auth login       # opens browser — log in with your Google account
  gcloud auth application-default login   # grants Terraform access to your credentials
  gcloud config set project vox-nutrition-prod  # set your default project
  ```
- [ ] **Terraform** >= 1.5.0 installed
  ```powershell
  # Install: https://developer.hashicorp.com/terraform/install (Windows AMD64)
  # Extract terraform.exe to a folder on your PATH (e.g. C:\tools\)
  terraform version
  ```
- [ ] **Docker** running (same Docker Desktop from Phase 1)
- [ ] `driver/` folder populated (same as Phase 1)

---

## Step 1 — Terraform setup

Terraform reads a `terraform.tfvars` file (like a `.env` for infrastructure), creates all the GCP resources, and outputs the commands you'll need for the next steps.

### 1.1 Create `terraform.tfvars`

```powershell
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and fill in your values:

```hcl
gcp_project    = "your-gcp-project-id"       # ← the Project ID, not display name
bq_dataset     = "plex_dataset"
bq_table       = "raw_materials_parts"
plex_host      = "odbc.plex.com"              # production Plex ODBC host
plex_odbc_user = "edominguez.parasol"         # Plex login (username.company)
image_url      = "us-central1-docker.pkg.dev/your-gcp-project-id/plex-pipeline/etl:latest"
```

> **`image_url` before pushing:** Set it to the correct format now even though the image doesn't exist yet. Terraform creates the Cloud Run job definition and you'll push the actual image in Step 3. The job will show an error if triggered before then, which is expected.

### 1.2 Initialize and apply

```powershell
terraform init      # downloads the Google provider plugin (like npm install)
terraform plan -var-file=terraform.tfvars   # dry-run: shows what will be created
terraform apply -var-file=terraform.tfvars  # actually creates everything
```

Type `yes` when prompted. Takes 2–5 minutes — API enablement is the slowest part.

**What Terraform just created:**
- A service account (`plex-etl-sa`) with permissions to read secrets, write to BigQuery, and pull from Artifact Registry
- A BigQuery dataset and `sync_metadata` table
- An Artifact Registry repo to store your Docker image
- Four Secret Manager secret containers (empty for now — you'll fill them in 1.3)
- A Cloud Run job definition pointing at your image
- A Cloud Scheduler job on a daily cron

> **If apply fails "API not yet enabled":** GCP API enablement is eventually consistent. Wait 60 seconds and re-run `terraform apply`.

> **If apply fails "image not found":** That's expected on first run if the image hasn't been pushed yet. Push the image (Step 3) and re-run `terraform apply`.

**Verify in GCP Console** (optional but helpful):
- Console → **IAM & Admin → Service Accounts** → you should see `plex-etl-sa@...`
- Console → **BigQuery** → your project → `plex_dataset` dataset
- Console → **Secret Manager** → four secrets: `plex-access-token`, `plex-odbc-user`, `plex-odbc-password`, `plex-company-code` (all with 0 versions — they're empty containers)

### 1.3 Store the IAM token in Secret Manager

Terraform creates the secret *container* but doesn't put any value in it. Add your Plex IAM token:

```powershell
# Replace the token string with the value from PLEX_ACCESS_TOKEN in your .env
echo -n 'Mjc4MDIyN2Et...' | gcloud secrets versions add plex-access-token `
  --data-file=- --project=your-gcp-project-id
```

Verify it was stored:
```powershell
gcloud secrets versions list plex-access-token --project=your-gcp-project-id
# Expected output:
#   NAME                                                              STATE    CREATED
#   projects/.../secrets/plex-access-token/versions/1    enabled  2026-06-...
```

> **GCP Console path:** Console → **Secret Manager** → `plex-access-token` → **Versions** tab → you should see version 1 with status "Enabled".

> **Token rotation:** When you get a new Plex IAM token, add it as a new version — Cloud Run automatically picks up the `latest` version on the next run:
> ```powershell
> echo -n 'NEW_TOKEN_VALUE' | gcloud secrets versions add plex-access-token --data-file=- --project=your-gcp-project-id
> ```

---

## Step 2 — Build and push the Docker image

Run from the **repo root** (not the `terraform/` folder):

```powershell
# Authenticate Docker to your Artifact Registry region
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build — replace the project ID with yours
docker build -t us-central1-docker.pkg.dev/your-gcp-project-id/plex-pipeline/etl:latest .

# Push to Artifact Registry (this is what Cloud Run will pull from)
docker push us-central1-docker.pkg.dev/your-gcp-project-id/plex-pipeline/etl:latest
```

> This can take 3–8 minutes on first push because of the ODBC driver files. Subsequent pushes are faster (layer caching).

Then re-apply Terraform so the Cloud Run job picks up the now-real image:

```powershell
cd terraform
terraform apply -var-file=terraform.tfvars
```

**Verify in GCP Console:** Console → **Artifact Registry** → `plex-pipeline` repo → you should see an `etl` image with a recent timestamp.

---

## Step 3 — Test the Cloud Run job manually

```powershell
gcloud run jobs execute plex-etl `
  --region=us-central1 `
  --project=your-gcp-project-id `
  --wait
```

The `--wait` flag keeps the terminal open until the job finishes (or fails). It takes about 30–60 seconds.

Check the logs:
```powershell
gcloud logging read `
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl" `
  --project=your-gcp-project-id `
  --limit=50 `
  --format="table(timestamp,textPayload)"
```

**Expected success log sequence:**
```
[INFO] Fetching credentials...
[INFO] Using IAM access token for Plex authentication.
[INFO] Connecting driver-direct to odbc.plex.com:19995 (IAM token auth, UID=edominguez.parasol)
[INFO] ODBC connection established.
[INFO] Querying Plex [Part_v_Part] for Raw Materials parts...
[INFO] Fetched NNN Raw Materials parts from Plex.
[INFO] Writing NNN rows to your-gcp-project-id.plex_dataset.raw_materials_parts...
[INFO] === ETL job complete — NNN rows written ===
```

**GCP Console path for logs:** Console → **Cloud Run** → **Jobs** tab → `plex-etl` → click the execution → **Logs** tab. This is often easier to read than the CLI output.

---

## Step 4 — Verify data in BigQuery

```powershell
bq query --project_id=your-gcp-project-id --nouse_legacy_sql `
  "SELECT COUNT(*) AS part_count FROM \`your-gcp-project-id.plex_dataset.raw_materials_parts\`"

bq query --project_id=your-gcp-project-id --nouse_legacy_sql `
  "SELECT Part_No, Name, Part_Status FROM \`your-gcp-project-id.plex_dataset.raw_materials_parts\` LIMIT 10"
```

**GCP Console path:** Console → **BigQuery** → your project → `plex_dataset` → `raw_materials_parts` → **Preview** tab shows the first 50 rows without writing a query.

---

## Step 5 — Verify Cloud Scheduler

Terraform creates a scheduler job at `0 2 * * *` (2 AM UTC daily):

```powershell
gcloud scheduler jobs list --location=us-central1 --project=your-gcp-project-id
```

Trigger it immediately to confirm end-to-end scheduling works:
```powershell
gcloud scheduler jobs run plex-daily-sync --location=us-central1 --project=your-gcp-project-id
```

> This runs the Cloud Run job the same way the scheduler will — it's a safe test to run anytime.

**GCP Console path:** Console → **Cloud Scheduler** → `plex-daily-sync` → **Run now** button does the same thing.

---

## Step 6 — CI/CD with Cloud Build (optional)

Cloud Build automates build → push → deploy every time you push to `main`. Without it, you re-run the `docker build/push` commands manually after each code change.

`deploy/cloudbuild.yaml` is already written. You just need to:

**1. Store the driver in GCS** (avoids committing the binary files to git):
```powershell
# Create the storage bucket
gcloud storage buckets create gs://your-gcp-project-id-build-assets --project=your-gcp-project-id

# Upload the driver folder
gcloud storage cp -r driver/* gs://your-gcp-project-id-build-assets/plex-odbc-driver/
```

**2. Create a Cloud Build trigger in GCP Console:**
- Console → **Cloud Build** → **Triggers** → **Create trigger**
- Name: `plex-etl-deploy`
- Region: `us-central1`
- Event: **Push to a branch**
- Source: connect your repo (GitHub/GitLab) — follow the OAuth flow
- Branch: `^main$`
- Configuration: **Cloud Build configuration file** → `deploy/cloudbuild.yaml`
- Click **Create**

After this, every `git push origin main` automatically rebuilds and redeploys the container. The trigger also runs a smoke test (executes the job and waits) — if the job fails, the build is marked as failed.

**Verify in GCP Console:** Console → **Cloud Build** → **History** — shows each build with pass/fail status and full logs.

---

## Troubleshooting

### `Secret not found` or `Permission denied on secret`

The secret exists but either (a) has no version yet or (b) the service account lacks access.

Check that version 1 was added (Step 1.3):
```powershell
gcloud secrets versions list plex-access-token --project=your-gcp-project-id
```

Check that the service account has the right permission:
```powershell
gcloud projects get-iam-policy your-gcp-project-id `
  --flatten="bindings[].members" `
  --filter="bindings.members:plex-etl-sa@"
```
You should see `roles/secretmanager.secretAccessor` in the output.

### Cloud Run job: ODBC connection error

- Confirm `plex_host` in `terraform.tfvars` is `odbc.plex.com` (not the test host)
- Cloud Run uses variable egress IPs — if Plex restricts connections by IP, you need a VPC connector + Cloud NAT to get a fixed outbound IP, then allowlist it with Plex support. This is an uncommon but known issue.

### Cloud Run job: table is empty after a failure

`WRITE_TRUNCATE` replaces the entire table on each run. If a job fails mid-write, the table may be empty until the next successful run. This is expected behavior for a full-refresh table — the next run restores it. To prevent data loss windows in production, the safer pattern is to load into a staging table first and swap with `CREATE OR REPLACE TABLE ... AS SELECT` — but that requires more code changes.

### Terraform: `Error: Provider configuration`

Make sure you've run `gcloud auth application-default login` (not just `gcloud auth login`). Terraform uses Application Default Credentials, which is a separate login flow.

### Terraform: `Error acquiring the state lock`

Terraform state is stored locally in `terraform/terraform.tfstate`. If a previous `apply` was interrupted, a lock file may remain. Delete `terraform/.terraform.lock.hcl` and retry.

---

## Operational runbook

**Rotate the IAM token:**
```powershell
echo -n 'NEW_TOKEN' | gcloud secrets versions add plex-access-token --data-file=- --project=your-gcp-project-id
```

**Change the sync schedule** (e.g. run at 6 AM UTC instead of 2 AM):
Update `scheduler_cron = "0 6 * * *"` in `terraform.tfvars`, then:
```powershell
cd terraform
terraform apply -var-file=terraform.tfvars
```

**Pause the pipeline** (stops the scheduler without deleting anything):
```powershell
gcloud scheduler jobs pause plex-daily-sync --location=us-central1 --project=your-gcp-project-id
```

**Resume the pipeline:**
```powershell
gcloud scheduler jobs resume plex-daily-sync --location=us-central1 --project=your-gcp-project-id
```

**View recent job history:**
```powershell
gcloud run jobs executions list --job=plex-etl --region=us-central1 --project=your-gcp-project-id
```

**Add a second Plex table:**
1. Add a new `query_plex()` variant (or make the view name configurable via env var)
2. Create a second Cloud Run job in Terraform pointing at the new table name
3. Define the BigQuery schema for the new table explicitly
