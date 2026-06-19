# GCP Deployment Guide — Phase 2

## What this gets you

By the end of this guide:

- All GCP infrastructure provisioned by Terraform in project `parasoldatalake`
- Docker image built and pushed to Artifact Registry
- Plex IAM token stored in Secret Manager
- Cloud Run job executing successfully against Plex and writing to BigQuery
- Cloud Scheduler running on a daily cron schedule

---

## Shell compatibility note

All multi-line commands in this guide use **backslash `\`** for line continuation — this works in **Git Bash, bash, and zsh**. If you are in PowerShell, replace `\` with a backtick `` ` ``.

```bash
# Git Bash / bash — use backslash
gcloud run jobs execute plex-etl \
  --region=us-central1 \
  --project=parasoldatalake

# PowerShell — use backtick
gcloud run jobs execute plex-etl `
  --region=us-central1 `
  --project=parasoldatalake
```

When in doubt, put everything on one line — it always works in both shells.

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
- [ ] **GCP project** `parasoldatalake` with billing enabled
  - In GCP Console: top-left dropdown → **New Project** → note the **Project ID** (like `parasoldatalake`) — this is different from the display name
  - Billing: GCP Console → **Billing** → link a billing account to the project
- [ ] **`gcloud` CLI** installed and authenticated
  ```bash
  gcloud version          # verify install
  gcloud auth login       # opens browser — log in with your Google account
  gcloud auth application-default login   # grants Terraform access to your credentials
  gcloud config set project parasoldatalake
  ```
- [ ] **Terraform** >= 1.5.0 installed and on your PATH
  ```bash
  terraform version
  ```
- [ ] **Docker** running (same Docker Desktop from Phase 1)
- [ ] `driver/` folder populated (same as Phase 1)

---

## Step 1 — Terraform setup

Terraform reads a `terraform.tfvars` file (like a `.env` for infrastructure), creates all the GCP resources, and outputs the commands you'll need for the next steps.

### 1.1 Create `terraform.tfvars`

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and confirm your values. For this project, the file should contain:

```hcl
gcp_project    = "parasoldatalake"
gcp_region     = "us-central1"
bq_dataset     = "plex_sandbox"
bq_table       = "raw_materials_parts"
plex_host      = "vox.odbc.plex.com"     # test host — change to odbc.plex.com for production
plex_odbc_user = "edominguez.parasol"
image_url      = "us-central1-docker.pkg.dev/parasoldatalake/plex-pipeline/etl:latest"
```

> **`image_url` before pushing:** Set it to the correct format now even though the image doesn't exist yet. Terraform creates the Cloud Run job definition and you'll push the actual image in Step 2. The job will show an error if triggered before then, which is expected.

### 1.2 Initialize and apply

```bash
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

Type `yes` when prompted. Takes 2–5 minutes — API enablement is the slowest part.

**What Terraform creates:**
- A service account (`plex-etl-sa`) with permissions to read secrets, write to BigQuery, and pull from Artifact Registry
- A BigQuery dataset and `sync_metadata` table
- An Artifact Registry repo to store your Docker image
- Four Secret Manager secret containers (empty for now — you'll fill them in 1.3)
- A Cloud Run job definition pointing at your image
- A Cloud Scheduler job on a daily cron

> **If apply fails "API not yet enabled":** GCP API enablement is eventually consistent. Wait 60 seconds and re-run `terraform apply`.

> **If apply fails "image not found":** Expected on first run. Push the image (Step 2) and re-run `terraform apply`.

**Verify in GCP Console:**
- Console → **IAM & Admin → Service Accounts** → you should see `plex-etl-sa@parasoldatalake.iam.gserviceaccount.com`
- Console → **BigQuery** → `parasoldatalake` → `plex_sandbox` dataset
- Console → **Secret Manager** → four secrets: `plex-access-token`, `plex-odbc-user`, `plex-odbc-password`, `plex-company-code` (all with 0 versions — empty containers)

### 1.3 Store the IAM token in Secret Manager

Terraform creates the secret *container* but doesn't put any value in it. Add your Plex IAM token:

```bash
echo -n '<YOUR_PLEX_IAM_TOKEN>' | gcloud secrets versions add plex-access-token \
  --data-file=- --project=parasoldatalake
```

Paste the token from your `.env` file (`PLEX_ACCESS_TOKEN=...`) in place of `<YOUR_PLEX_IAM_TOKEN>`.

Verify it was stored:
```bash
gcloud secrets versions list plex-access-token --project=parasoldatalake
# Expected:
#   NAME    STATE    CREATED
#   1       enabled  2026-06-...
```

> **GCP Console path:** Console → **Secret Manager** → `plex-access-token` → **Versions** tab → version 1, status "Enabled".

> **Token rotation:** When you get a new Plex IAM token, add a new version — Cloud Run picks up `latest` automatically:
> ```bash
> echo -n 'NEW_TOKEN_VALUE' | gcloud secrets versions add plex-access-token --data-file=- --project=parasoldatalake
> ```

### 1.4 If resources already exist (state recovery)

If `terraform apply` fails with `Error 409: Already Exists` for secrets or the BigQuery dataset, Terraform's state is out of sync with reality. Import the existing resources before re-running apply:

```bash
# Import secrets
terraform import google_secret_manager_secret.access_token projects/parasoldatalake/secrets/plex-access-token
terraform import google_secret_manager_secret.odbc_user projects/parasoldatalake/secrets/plex-odbc-user
terraform import google_secret_manager_secret.odbc_password projects/parasoldatalake/secrets/plex-odbc-password
terraform import google_secret_manager_secret.company_code projects/parasoldatalake/secrets/plex-company-code

# Import BigQuery dataset (replace plex_sandbox with your dataset name if different)
terraform import google_bigquery_dataset.plex parasoldatalake/plex_sandbox
```

Then re-run `terraform apply`. If the state file is badly corrupted (references the wrong project entirely), delete it and reimport everything:

```bash
rm terraform.tfstate terraform.tfstate.backup   # wipe stale state
# then run all imports above before apply
```

---

## Step 2 — Build and push the Docker image

Run from the **repo root** (not the `terraform/` folder):

```bash
# Authenticate Docker to your Artifact Registry region
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build the image
docker build -t us-central1-docker.pkg.dev/parasoldatalake/plex-pipeline/etl:latest .

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/parasoldatalake/plex-pipeline/etl:latest
```

> This takes 3–8 minutes on first push because of the ODBC driver files. Subsequent pushes are faster (layer caching).

Then re-apply Terraform so the Cloud Run job picks up the now-real image:

```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

**Verify in GCP Console:** Console → **Artifact Registry** → `plex-pipeline` repo → you should see an `etl` image with a recent timestamp.

---

## Step 3 — Test the Cloud Run job manually

```bash
gcloud run jobs execute plex-etl --region=us-central1 --project=parasoldatalake --wait
```

The `--wait` flag keeps the terminal open until the job finishes (or fails). Takes about 30–60 seconds.

Check the logs:
```bash
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl" \
  --project=parasoldatalake \
  --limit=50 \
  --format="table(timestamp,textPayload)"
```

**Expected success log sequence:**
```
[INFO] Fetching credentials...
[INFO] Using IAM access token for Plex authentication.
[INFO] Connecting driver-direct to vox.odbc.plex.com:19995 (IAM token auth, UID=edominguez.parasol)
[INFO] ODBC connection established.
[INFO] Querying Plex [Part_v_Part] for Raw Materials parts...
[INFO] Fetched NNN Raw Materials parts from Plex.
[INFO] Writing NNN rows to parasoldatalake.plex_sandbox.raw_materials_parts...
[INFO] === ETL job complete — NNN rows written ===
```

**GCP Console path for logs:** Console → **Cloud Run** → **Jobs** tab → `plex-etl` → click the execution → **Logs** tab.

---

## Step 4 — Verify data in BigQuery

```bash
bq query --project_id=parasoldatalake --nouse_legacy_sql \
  "SELECT COUNT(*) AS part_count FROM \`parasoldatalake.plex_sandbox.raw_materials_parts\`"

bq query --project_id=parasoldatalake --nouse_legacy_sql \
  "SELECT Part_No, Name, Part_Status FROM \`parasoldatalake.plex_sandbox.raw_materials_parts\` LIMIT 10"
```

**GCP Console path:** Console → **BigQuery** → `parasoldatalake` → `plex_sandbox` → `raw_materials_parts` → **Preview** tab.

---

## Step 5 — Verify Cloud Scheduler

Terraform creates a scheduler job at `0 2 * * *` (2 AM UTC daily):

```bash
gcloud scheduler jobs list --location=us-central1 --project=parasoldatalake
```

Trigger it immediately to confirm end-to-end scheduling works:
```bash
gcloud scheduler jobs run plex-daily-sync --location=us-central1 --project=parasoldatalake
```

**GCP Console path:** Console → **Cloud Scheduler** → `plex-daily-sync` → **Run now** button.

---

## Step 6 — CI/CD with Cloud Build (optional)

Cloud Build automates build → push → deploy every time you push to `main`. Without it, you re-run the `docker build/push` commands manually after each code change.

`deploy/cloudbuild.yaml` is already written. You just need to:

**1. Store the driver in GCS** (avoids committing the binary files to git):
```bash
gcloud storage buckets create gs://parasoldatalake-build-assets --project=parasoldatalake
gcloud storage cp -r driver/* gs://parasoldatalake-build-assets/plex-odbc-driver/
```

**2. Create a Cloud Build trigger in GCP Console:**
- Console → **Cloud Build** → **Triggers** → **Create trigger**
- Name: `plex-etl-deploy`
- Region: `us-central1`
- Event: **Push to a branch**
- Source: connect your repo (GitHub) — follow the OAuth flow
- Branch: `^main$`
- Configuration: **Cloud Build configuration file** → `deploy/cloudbuild.yaml`
- Click **Create**

After this, every `git push origin main` automatically rebuilds and redeploys the container.

---

## Troubleshooting

### `Secret not found` or `Permission denied on secret`

The secret exists but either has no version or the service account lacks access.

Check that version 1 was added (Step 1.3):
```bash
gcloud secrets versions list plex-access-token --project=parasoldatalake
```

Check that the service account has the right permission:
```bash
gcloud projects get-iam-policy parasoldatalake \
  --flatten="bindings[].members" \
  --filter="bindings.members:plex-etl-sa@"
```
You should see `roles/secretmanager.secretAccessor` in the output.

### Error 10300: `The requested service was not found in the provided configuration`

The `ServerDataSource` name in the ODBC connection string doesn't match what the Plex server has configured.

- **This means your token or PLEX_HOST points to one environment but the service name belongs to another.**
- `ReportDataSource` works on `vox.odbc.plex.com` (test).
- The production host `odbc.plex.com` likely uses a different name — confirm with Plex support.

To switch Cloud Run to the test host temporarily for validation:
```bash
gcloud run jobs update plex-etl \
  --region=us-central1 \
  --project=parasoldatalake \
  --update-env-vars=PLEX_HOST=vox.odbc.plex.com
```

To update the ServerDataSource once you have the correct name from Plex support:
```bash
gcloud run jobs update plex-etl \
  --region=us-central1 \
  --project=parasoldatalake \
  --update-env-vars=PLEX_SERVER_DATASOURCE=<name-from-plex-support>
```

### Cloud Run job: table is empty after a failure

`WRITE_TRUNCATE` replaces the entire table on each run. If a job fails mid-write, the table may be empty until the next successful run. This is expected behavior for a full-refresh table.

### Terraform: `Error: Provider configuration`

Make sure you've run `gcloud auth application-default login` (not just `gcloud auth login`). Terraform uses Application Default Credentials, which is a separate login flow.

### Terraform: `Error acquiring the state lock`

Terraform state is stored locally in `terraform/terraform.tfstate`. If a previous `apply` was interrupted, a lock file may remain. Delete `terraform/.terraform.lock.hcl` and retry.

---

## Operational runbook

**Rotate the IAM token:**
```bash
echo -n 'NEW_TOKEN' | gcloud secrets versions add plex-access-token --data-file=- --project=parasoldatalake
```

**Change the sync schedule** (e.g. run at 6 AM UTC instead of 2 AM):
Update `scheduler_cron = "0 6 * * *"` in `terraform.tfvars`, then:
```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

**Pause the pipeline:**
```bash
gcloud scheduler jobs pause plex-daily-sync --location=us-central1 --project=parasoldatalake
```

**Resume the pipeline:**
```bash
gcloud scheduler jobs resume plex-daily-sync --location=us-central1 --project=parasoldatalake
```

**View recent job history:**
```bash
gcloud run jobs executions list --job=plex-etl --region=us-central1 --project=parasoldatalake
```

**Switch to production Plex host** (once confirmed with Plex support):
```bash
gcloud run jobs update plex-etl \
  --region=us-central1 \
  --project=parasoldatalake \
  --update-env-vars=PLEX_HOST=odbc.plex.com,PLEX_SERVER_DATASOURCE=<production-service-name>
```
Then update `terraform.tfvars` to match so the next `terraform apply` doesn't revert the change.

**Tear down all infrastructure** (move to a different GCP project):
See [docs/TEARDOWN.md](docs/TEARDOWN.md) for the full procedure, including unlocking Terraform-protected resources and redeploying to a new project.

**Add a second Plex table:**
1. Add a new `query_plex()` variant (or make the view name configurable via env var)
2. Create a second Cloud Run job in Terraform pointing at the new table name
3. Define the BigQuery schema for the new table explicitly
