# GCP Deployment Guide — Phase 2

> **Scope check:** this walks through bootstrapping the pipeline **from
> zero** — the original single-view job (`plex-etl-sales-orders` / `Part_v_Part`), one
> Cloud Run job, one schedule. It's the right doc for a first-time setup
> (a new GCP project, disaster recovery) or for understanding how the
> pieces fit together. If you're adding a **new report to an
> already-running deployment**, this isn't that doc — see
> [docs/OPERATIONS.md](OPERATIONS.md) § "Add a Brand-New Report" instead
> (referenced again at the bottom of this guide).

## What this gets you

By the end of this guide:

- All GCP infrastructure provisioned by Terraform in project `voxdatalake`
- Docker image built and pushed to Artifact Registry
- Plex IAM token stored in Secret Manager
- Cloud Run job executing successfully against Plex and writing to BigQuery
- Cloud Scheduler running on a daily cron schedule

---

## Shell compatibility note

All multi-line commands in this guide use **backslash `\`** for line continuation — this works in **Git Bash, bash, and zsh**. If you are in PowerShell, replace `\` with a backtick `` ` ``.

```bash
# Git Bash / bash — use backslash
gcloud run jobs execute plex-etl-sales-orders \
  --region=us-central1 \
  --project=voxdatalake

# PowerShell — use backtick
gcloud run jobs execute plex-etl-sales-orders `
  --region=us-central1 `
  --project=voxdatalake
```

When in doubt, put everything on one line — it always works in both shells.

---

## How the GCP pieces fit together

If you're coming from frontend, here's a mental model for each service this pipeline uses:

| GCP Service | Think of it like… | What it does here |
|---|---|---|
| **Artifact Registry** | npm registry / Docker Hub | Stores your built Docker image |
| **Cloud Run Job** | Vercel/Lambda serverless function | Runs the ETL container on demand |
| **Cloud Scheduler** | `cron` / GitHub Actions schedule | Triggers the Cloud Run job daily — this deployment's actual schedule cascades all 8 report categories through a 7:00 PM-9:45 PM America/Denver (Mountain) window, see [docs/EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md) for the full per-category breakdown |
| **BigQuery** | Postgres / Supabase (analytics-focused, read-heavy) | Stores the extracted Plex data as queryable tables |
| **Secret Manager** | `.env` file, but encrypted + access-controlled | Holds the Plex IAM token and ODBC credentials |
| **Service Account** | API key your app authenticates with | What Cloud Run uses to talk to BigQuery, Secret Manager, etc. |
| **Terraform** | `npm install` for cloud infra | Provisions all of the above with a single `terraform apply` |

> **Two kinds of tokens:** There are two separate authentication systems at play. The **Plex IAM token** (`plex-access-token`) is how the ETL script authenticates to the Plex ERP ODBC endpoint — you store this in Secret Manager. The **GCP service account** is how Cloud Run authenticates to GCP services (BigQuery, Secret Manager) — Terraform creates this automatically. You never see the service account token directly.

---

## Prerequisites checklist

- [ ] **Phase 1 complete** — `docker compose up` ran locally and produced a CSV in `./output/`
- [ ] **GCP project** `voxdatalake` with billing enabled
  - In GCP Console: top-left dropdown → **New Project** → note the **Project ID** (like `voxdatalake`) — this is different from the display name
  - Billing: GCP Console → **Billing** → link a billing account to the project
- [ ] **`gcloud` CLI** installed and authenticated
  ```bash
  gcloud version          # verify install
  gcloud auth login       # opens browser — log in with your Google account
  gcloud auth application-default login   # grants Terraform access to your credentials
  gcloud config set project voxdatalake
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
gcp_project    = "voxdatalake"
gcp_region     = "us-central1"
bq_dataset     = "PlexTest"
bq_table       = "raw_Part_v_Part"
plex_host      = "vox.test.odbc.plex.com"     # test host — change to vox.odbc.plex.com for production
plex_odbc_user = "edominguez.parasol"
image_url      = "us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest"
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
- Console → **IAM & Admin → Service Accounts** → you should see `plex-etl-sa@voxdatalake.iam.gserviceaccount.com`
- Console → **BigQuery** → `voxdatalake` → `PlexTest` dataset
- Console → **Secret Manager** → four secrets: `plex-access-token`, `plex-odbc-user`, `plex-odbc-password`, `plex-company-code` (all with 0 versions — empty containers)

### 1.3 Store the IAM token in Secret Manager

Terraform creates the secret *container* but doesn't put any value in it. Add your Plex IAM token:

```bash
echo -n '<YOUR_PLEX_IAM_TOKEN>' | gcloud secrets versions add plex-access-token \
  --data-file=- --project=voxdatalake
```

Paste the token from your `.env` file (`PLEX_ACCESS_TOKEN=...`) in place of `<YOUR_PLEX_IAM_TOKEN>`.

Verify it was stored:
```bash
gcloud secrets versions list plex-access-token --project=voxdatalake
# Expected:
#   NAME    STATE    CREATED
#   1       enabled  2026-06-...
```

> **GCP Console path:** Console → **Secret Manager** → `plex-access-token` → **Versions** tab → version 1, status "Enabled".

> **Token rotation:** When you get a new Plex IAM token, add a new version — Cloud Run picks up `latest` automatically:
> ```bash
> echo -n 'NEW_TOKEN_VALUE' | gcloud secrets versions add plex-access-token --data-file=- --project=voxdatalake
> ```

### 1.4 If resources already exist (state recovery)

If `terraform apply` fails with `Error 409: Already Exists` for secrets or the BigQuery dataset, Terraform's state is out of sync with reality. Import the existing resources before re-running apply:

```bash
# Import secrets
terraform import google_secret_manager_secret.access_token projects/voxdatalake/secrets/plex-access-token
terraform import google_secret_manager_secret.odbc_user projects/voxdatalake/secrets/plex-odbc-user
terraform import google_secret_manager_secret.odbc_password projects/voxdatalake/secrets/plex-odbc-password
terraform import google_secret_manager_secret.company_code projects/voxdatalake/secrets/plex-company-code

# Import BigQuery dataset (replace PlexTest with your dataset name if different)
terraform import google_bigquery_dataset.plex voxdatalake/PlexTest
```

Then re-run `terraform apply`. If the state is badly corrupted (references the wrong project entirely):

**State lives in a shared GCS backend** (`gs://voxdatalake-terraform-state/plex-to-big-query/default.tfstate`), not a local file — there is no `terraform.tfstate` to delete locally anymore. The bucket has **object versioning enabled**, so the safer first move is rolling back to a previous version rather than wiping it:

```bash
# List previous versions of the state object
gcloud storage ls -a gs://voxdatalake-terraform-state/plex-to-big-query/default.tfstate

# Restore a specific earlier version (copy it back over the live object)
gcloud storage cp gs://voxdatalake-terraform-state/plex-to-big-query/default.tfstate#GENERATION_NUMBER \
  gs://voxdatalake-terraform-state/plex-to-big-query/default.tfstate
```

Only as a last resort, wipe it entirely and reimport everything:
```bash
gcloud storage rm gs://voxdatalake-terraform-state/plex-to-big-query/default.tfstate
terraform init   # recreates an empty state at the same backend path
# then run all imports above before apply
```

---

## Step 2 — Build and push the Docker image

### About the Docker image

The image contains everything needed to run the ETL in a Linux container:

- **Python 3.11** (base image)
- **unixODBC** driver manager — the Linux ODBC standard
- **DataDirect OpenAccess SDK 8.1** — the actual Plex ODBC driver (`ivoa27.so`), copied from your local `driver/` folder into `/usr/oaodbc81/lib64/` inside the container
- **Python packages** — `pyodbc`, `pandas`, `google-cloud-bigquery`, `sendgrid` (from `requirements.txt`)
- **App code** — `main.py`, `email_utils.py`, `templates/`

The ODBC driver is **not in git** — it must be present in `driver/` on your machine before building. If the folder is missing, `docker build` will fail at the `COPY driver/` step. Obtain the Linux 64-bit driver from the Plex support portal.

### What "rebuilding" means

**Not true as of 2026-08-13** — pushing a new image does NOT get picked up automatically. Cloud Run Jobs resolve the image to a digest at *update* time, not at each execution, and every job's Terraform resource now has `lifecycle { ignore_changes = [image] }` specifically so a routine `terraform apply` can't silently move it either. After pushing, explicitly redeploy each job you want on the new build:
```bash
gcloud run jobs update JOB_NAME --image=us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:TAG --region=us-central1
```
`deploy/cloudbuild.yaml`'s `deploy-all` step does this for all 16 jobs from one build. Use a commit-SHA tag, never `:latest` — see `variables.tf`'s `image_url` description for why.

You only need to rebuild when **code or files inside the image change**:
- `main.py`, `email_utils.py`, `templates/report.html` — Python logic or email design
- `requirements.txt` — a new Python package
- `driver/` — a new Plex ODBC driver version
- `config/odbcinst.ini` or `config/odbc.ini` — ODBC config changes

For everything else (Plex host, table name, email addresses, company name), edit `terraform.tfvars` and run `terraform apply`. No rebuild needed.

### Build and push commands

Run from the **repo root** (not the `terraform/` folder):

```bash
# Authenticate Docker to your Artifact Registry region
gcloud auth configure-docker us-central1-docker.pkg.dev --project=voxdatalake

# Tag with the current commit SHA — never ":latest" (see variables.tf's
# image_url description). ":latest" is still pushed alongside for
# convenience/manual `docker pull` only; nothing deployed ever reads it.
SHA=$(git rev-parse --short HEAD)
docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA \
             -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest .

# Push both tags to Artifact Registry
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest
```

> First push takes 3–8 minutes because of the ODBC driver files (~40 MB). Subsequent pushes are faster — Docker reuses cached layers for anything that didn't change.

Set `image_url` in `terraform.tfvars` to that same `:$SHA` tag, then apply — this is what creates the Cloud Run job on this first pass. On every later rebuild, this `terraform apply` step does **not** redeploy anything by itself (each job's `lifecycle { ignore_changes }` on `image` sees to that) — you'd explicitly `gcloud run jobs update JOB_NAME --image=...` instead, or let `deploy/cloudbuild.yaml`'s `deploy-all` step do it for all jobs at once:

```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

**Verify in GCP Console:** Console → **Artifact Registry** → `plex-pipeline` repo → you should see an `etl` image with a recent timestamp.

---

## Step 3 — Test the Cloud Run job manually

```bash
gcloud run jobs execute plex-etl-sales-orders --region=us-central1 --project=voxdatalake --wait
```

The `--wait` flag keeps the terminal open until the job finishes (or fails). Takes about 30–60 seconds.

Check the logs:
```bash
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl-sales-orders" \
  --project=voxdatalake \
  --limit=50 \
  --format="table(timestamp,textPayload)"
```

**Expected success log sequence:**
```
[INFO] Fetching credentials...
[INFO] Using IAM access token for Plex authentication.
[INFO] Connecting driver-direct to vox.test.odbc.plex.com:19995 (IAM token auth, UID=edominguez.parasol)
[INFO] ODBC connection established.
[INFO] Querying Plex [Part_v_Part] for Raw Materials parts...
[INFO] Fetched NNN Raw Materials parts from Plex.
[INFO] Writing NNN rows to voxdatalake.PlexTest.raw_Part_v_Part...
[INFO] === ETL job complete — NNN rows written ===
```

**GCP Console path for logs:** Console → **Cloud Run** → **Jobs** tab → `plex-etl-sales-orders` → click the execution → **Logs** tab.

---

## Step 4 — Verify data in BigQuery

```bash
bq query --project_id=voxdatalake --nouse_legacy_sql \
  "SELECT COUNT(*) AS part_count FROM \`voxdatalake.PlexTest.raw_Part_v_Part\`"

bq query --project_id=voxdatalake --nouse_legacy_sql \
  "SELECT Part_No, Name, Part_Status FROM \`voxdatalake.PlexTest.raw_Part_v_Part\` LIMIT 10"
```

**GCP Console path:** Console → **BigQuery** → `voxdatalake` → `PlexTest` → `raw_Part_v_Part` → **Preview** tab.

---

## Step 5 — Verify Cloud Scheduler

Terraform creates a scheduler job at `0 2 * * *` (2 AM UTC daily) — that's `variables.tf`'s generic default for a from-scratch deploy. This live project's `terraform.tfvars` overrides `scheduler_cron`/`scheduler_time_zone` to a 7:00 PM-9:45 PM `America/Denver` (Mountain) cascade across all 8 report categories, so `gcloud scheduler jobs list` against `voxdatalake` today won't show 2 AM UTC — see [docs/EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md) for the actual per-category times:

```bash
gcloud scheduler jobs list --location=us-central1 --project=voxdatalake
```

Trigger it immediately to confirm end-to-end scheduling works:
```bash
gcloud scheduler jobs run plex-sales-orders-sync --location=us-central1 --project=voxdatalake
```

**GCP Console path:** Console → **Cloud Scheduler** → `plex-sales-orders-sync` → **Run now** button.

---

## Step 6 — CI/CD with Cloud Build (optional)

Cloud Build automates build → push → deploy every time you push to `main`. Without it, you re-run the `docker build/push` commands manually after each code change.

`deploy/cloudbuild.yaml` is already written. You just need to:

**1. Store the driver in GCS** (avoids committing the binary files to git):
```bash
gcloud storage buckets create gs://voxdatalake-build-assets --project=voxdatalake
gcloud storage cp -r driver/* gs://voxdatalake-build-assets/plex-odbc-driver/
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
gcloud secrets versions list plex-access-token --project=voxdatalake
```

Check that the service account has the right permission:
```bash
gcloud projects get-iam-policy voxdatalake \
  --flatten="bindings[].members" \
  --filter="bindings.members:plex-etl-sa@"
```
You should see `roles/secretmanager.secretAccessor` in the output.

### Error 10300: `The requested service was not found in the provided configuration`

The `ServerDataSource` name in the ODBC connection string doesn't match what the Plex server has configured.

- **This means your token or PLEX_HOST points to one environment but the service name belongs to another.**
- `ReportDataSource` works on `vox.test.odbc.plex.com` (test).
- The production host is `vox.odbc.plex.com` — confirm the correct `ServerDataSource` name with Plex support if this error appears on production.

To switch Cloud Run to the test host temporarily for validation:
```bash
gcloud run jobs update plex-etl-sales-orders \
  --region=us-central1 \
  --project=voxdatalake \
  --update-env-vars=PLEX_HOST=vox.test.odbc.plex.com
```

To update the ServerDataSource once you have the correct name from Plex support:
```bash
gcloud run jobs update plex-etl-sales-orders \
  --region=us-central1 \
  --project=voxdatalake \
  --update-env-vars=PLEX_SERVER_DATASOURCE=<name-from-plex-support>
```

### Cloud Run job: table is empty after a failure

`WRITE_TRUNCATE` replaces the entire table on each run. If a job fails mid-write, the table may be empty until the next successful run. This is expected behavior for a full-refresh table.

### Terraform: `Error: Provider configuration`

Make sure you've run `gcloud auth application-default login` (not just `gcloud auth login`). Terraform uses Application Default Credentials, which is a separate login flow.

### Terraform: `Error acquiring the state lock`

Terraform state is stored remotely in `gs://voxdatalake-terraform-state/plex-to-big-query/` (migrated 2026-07-20 — any team member with access to that bucket can safely run `plan`/`apply` from their own machine). If a previous `apply` was interrupted, GCS may still hold the lock. Check who/what holds it:

```bash
gcloud storage objects describe gs://voxdatalake-terraform-state/plex-to-big-query/default.tflock --project=voxdatalake
```

If the lock is genuinely stale (the process that created it is confirmed dead), force-unlock using the lock ID Terraform reports:
```bash
cd terraform && terraform force-unlock <LOCK_ID>
```

---

## Operational runbook

**Rotate the IAM token:**
```bash
echo -n 'NEW_TOKEN' | gcloud secrets versions add plex-access-token --data-file=- --project=voxdatalake
```

**Change the sync schedule** (e.g. run at a different Mountain-time hour instead of the current 7:00 PM cascade):
Update `scheduler_cron` and `scheduler_time_zone` in `terraform.tfvars`, then:
```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

**Pause the pipeline:**
```bash
gcloud scheduler jobs pause plex-sales-orders-sync --location=us-central1 --project=voxdatalake
```

**Resume the pipeline:**
```bash
gcloud scheduler jobs resume plex-sales-orders-sync --location=us-central1 --project=voxdatalake
```

**View recent job history:**
```bash
gcloud run jobs executions list --job=plex-etl-sales-orders --region=us-central1 --project=voxdatalake
```

**Switch to production Plex host** (once confirmed with Plex support):
```bash
gcloud run jobs update plex-etl-sales-orders \
  --region=us-central1 \
  --project=voxdatalake \
  --update-env-vars=PLEX_HOST=vox.odbc.plex.com,PLEX_SERVER_DATASOURCE=<production-service-name>
```
Then update `terraform.tfvars` to match so the next `terraform apply` doesn't revert the change.

**Tear down all infrastructure** (move to a different GCP project):
See [docs/TEARDOWN.md](docs/TEARDOWN.md) for the full procedure, including unlocking Terraform-protected resources and redeploying to a new project.

**Add a second Plex table / a whole new report:** this guide walks through bootstrapping the *original* single-view pipeline (`plex-etl-sales-orders` / `Part_v_Part`) from zero — it's not the process for adding to an already-running deployment. The project has since grown to 8 report families (16 Cloud Run jobs, prod+test) driven by YAML configs in GCS rather than hardcoded views, with no code changes needed for a new extraction. For that process:
- **Adding a new report from scratch:** [docs/OPERATIONS.md](OPERATIONS.md) § "Add a Brand-New Report" — the canonical, most detailed walkthrough (Plex view discovery, YAML/SQL scaffolding, `SAFE_CAST` patterns, shared-table rules).
- **Specifically tackling the next NetSuite-parity report:** [docs/NETSUITE_REPORT_BUILD_PLAN.md](NETSUITE_REPORT_BUILD_PLAN.md) § "Tackling the next NetSuite report" — the same process, with the NetSuite-specific investigative steps (saved-search criteria, business-rule confirmation) layered on top.
- **Condensed/quick-reference versions of the same steps:** [docs/CHEATSHEET.md](CHEATSHEET.md) § "How to Add a New Report" and [docs/CLICKUP_TEAM_GUIDE.md](CLICKUP_TEAM_GUIDE.md) § 6.
