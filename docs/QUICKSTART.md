# Quick Start Guide

Last reviewed: 2026-09-25

> **Who is this for?** Anyone setting up this pipeline for the first time with no prior knowledge of Docker, GCP, or ETL assumed. Every step tells you what you're doing and why, not just the commands to type.

---

## What are we building?

A pipeline that automatically pulls data from **Plex ERP** and stores it in **Google BigQuery** on a schedule. Once set up, it runs on its own forever — you don't touch it again unless something needs to change.

There are two phases:
1. **Local test** — get a single data pull working on your laptop (proves the connection works before deploying anything to the cloud). Pulls `Part_v_Part` by default — a simple, single-view example, not the actual production report.
2. **Cloud deploy** — provisions the real GCP infrastructure via Terraform.

> **Stop before Phase 2 if you are joining the existing `voxdatalake`
> project** (the usual case). Its infrastructure already exists, and Terraform
> state is shared (`gs://voxdatalake-terraform-state`) — running Phase 2 there
> would apply *your* `terraform.tfvars` over the live stack. Do Phase 1 to prove
> your setup works; after that, changes go through a `dev*` branch → `main` →
> `./scripts/deploy.sh` from the primary folder (`CONTRIBUTING.md` §
> "Branches, folders and locks"). Phase 2 is only for a **brand-new GCP
> project**.
>
> **Reality check for Phase 2:** the first deploy doesn't create just one job —
> `terraform/main.tf` defines all **26** Cloud Run jobs (13 pipelines ×
> prod/test) and 52 schedulers with no conditional gating, so one deploy stands
> up the entire stack at once. The job this guide walks through testing,
> `plex-etl-sales-orders`, runs the **Sales Orders** pipeline
> (`reports/sales_orders.yaml` — 27 Plex views) via `report_config_gcs_path`
> (already set in `terraform.tfvars.example`) — **not** a simple `Part_v_Part`
> puller. Phase 1's local test and Phase 2's deployed job pull different Plex
> views; that's intentional (Phase 1 proves basic connectivity with the
> simplest possible example). Sales Orders does extract `Part_v_Part` as one
> of its 27 views (into the shared `raw_Part_v_Part`, unfiltered, unlike Phase
> 1's Raw Materials filter), so look for its report tables instead — see Steps
> 9/13 below.

---

## What you'll need

Before you start, collect these things. Some require waiting on other people, so do this first.

### Things to install (you can do this now)

- [ ] **Docker Desktop** — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
  - After installing: right-click the tray icon, confirm it says "Switch to Windows containers" (that means you're already in the correct Linux mode)
- [ ] **Git** — [git-scm.com](https://git-scm.com/) (you probably already have this)
- [ ] **gcloud CLI** — [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install) (Windows installer)
- [ ] **Terraform** >= 1.5.0 — [developer.hashicorp.com/terraform/install](https://developer.hashicorp.com/terraform/install)
  - Download the Windows AMD64 zip, extract `terraform.exe`, put it in `C:\tools\`
  - Add `C:\tools\` to your PATH in System Settings → Environment Variables

### If you're joining the existing team project (most common)

The Plex ODBC driver (already licensed), credentials, and IAM token all
already exist for `voxdatalake` — you don't need to request anything from
Plex support. You need:

- [ ] **GCP access to the `voxdatalake` project** — ask whoever manages GCP
  access to grant you a role (see the team guide's access section for which
  role you need for what)
- [ ] `gcloud` CLI installed and authenticated (`gcloud auth login`)

Then skip straight to Step 2 below — the driver comes from a shared GCS
bucket, not from Plex support — and stop at the end of Phase 1 (see the box
at the top).

### If you're setting up a brand-new Plex integration (rare)

Only needed if there is no existing `voxdatalake`-style project yet:

- [ ] **Plex ODBC credentials:** username, password, CompanyCode
- [ ] **Linux ODBC driver files:** a `.zip` or `.tar` file containing the driver
- [ ] **IAM access token** for ODBC authentication (ask for IAM/token-based auth)
- [ ] **Confirmation of** the view name, column names, and whether you have read access

The old request-email template was removed in the 2026-07-21 docs reorg; it is still in git history: `git show c4eda6d^:PLEX_SUPPORT_TEMPLATE.md`.

### Things to set up in Google Cloud (requires a Google account with billing)

- [ ] **GCP project** named `voxdatalake` (or ask whoever manages your GCP account to create it)
- [ ] **Billing account linked** to the project (required to use most GCP services)

---

## Phase 1 — Get it working locally

### Step 1 · Get the repo

```bash
git clone <repo-url>
cd plex-to-big-query
```

### Step 2 · Put the ODBC driver files in the right place

The Plex ODBC driver is a set of Linux binary files that the Docker container uses to talk to Plex. The `driver/` folder is gitignored — you populate it locally.

**If you're joining the existing team project**, pull the already-licensed driver from the shared GCS bucket (same files Cloud Build uses):

```bash
gcloud storage cp -r gs://voxdatalake-build-assets/plex-odbc-driver/* driver/
```

When done, you should have:

```
driver/
  lib64/
    ivoa27.so       ← this file must exist
    ddtrc27.so
  etc/
    lang/
      usenglish.msg
  OAODBC64.LIC      ← driver license — only present via the GCS path above
```

**If you're setting up from scratch** (no shared bucket yet), extract the
driver package Plex support gave you into `driver/` instead. If it contains
a `.tar` file called `ivoaLinux64.tar`, extract it:

```bash
tar -xf driver/etc/tar/ivoaLinux64.tar -C driver/ lib64/
```

This path does not include a license file — see [LOCAL_SETUP.md](LOCAL_SETUP.md) and [archive/APPLY_DRIVER_LICENSE.md](archive/APPLY_DRIVER_LICENSE.md) if you need to apply one.

**How to check it worked:**
```bash
ls driver/lib64/
# Must show: ivoa27.so
```

If `ivoa27.so` is missing, the Docker build will fail. Fix this before continuing.

### Step 3 · Create your credentials file

Copy the template and fill it in:

```bash
cp .env.example .env
```

Open `.env` and set these values (the others can stay as defaults for now):

```env
PLEX_ACCESS_TOKEN=<token-from-plex-support>
PLEX_ODBC_USER=edominguez.parasol
PLEX_HOST=vox.test.odbc.plex.com
BQ_TABLE=raw_Part_v_Part
```

> **Security:** `.env` is in `.gitignore` — it will never be committed. Never paste it into Slack or email.

### Step 4 · Build the Docker image

```bash
docker compose build
```

This downloads the base Python image, installs system packages, copies the driver files, and installs the Python dependencies. **First build takes 5–10 minutes.** Subsequent builds are much faster.

**It worked if you see:** `... naming to ... etl:latest` at the end with no errors.

**Common failures:**

| Error message | Fix |
|---|---|
| `COPY driver/lib64` failed — file not found | `driver/lib64/ivoa27.so` is missing — redo Step 2 |
| `dpkg --add-architecture i386` failed | Docker is in Windows containers mode — switch to Linux mode (right-click tray icon) |
| `pip install` failed — network error | Check Docker Desktop proxy/firewall settings |

### Step 5 · Run it

```bash
docker compose up
```

The container runs once, connects to Plex, pulls the data, writes a CSV, and exits. Watch the terminal output for this sequence:

```
[INFO] LOCAL MODE — skipping BigQuery, full extract.
[INFO] Connecting driver-direct to vox.test.odbc.plex.com:19995 (IAM token auth)
[INFO] ODBC connection established.
[INFO] Querying Plex [Part_v_Part] for Raw Materials parts...
[INFO] Fetched 1234 Raw Materials parts from Plex.
[INFO] Wrote 1234 rows to /output/raw_Part_v_Part_20260619T020000Z.csv
[INFO] === ETL job complete — 1234 rows written ===
```

### Step 6 · Check the output

```bash
ls output/
# Shows: raw_Part_v_Part_20260619T020000Z.csv
```

Open the CSV and verify:
- Column names match what you expect from Plex
- Row count looks reasonable
- No entirely empty columns

**If this looks right, Phase 1 is done.** You've proven the connection works. Move to Phase 2.

---

## Phase 2 — Deploy to Google Cloud

### Step 7 · Log in to GCP

```bash
gcloud auth login                        # opens browser, log in with your Google account
gcloud auth application-default login    # Terraform needs this separate login
gcloud config set project voxdatalake
```

**Check it worked:**
```bash
gcloud config get-value project
# Should print: voxdatalake
```

### Step 8 · Set up Terraform config

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and confirm these values are correct:

```hcl
gcp_project    = "voxdatalake"
bq_dataset     = "PlexTest"
bq_table       = "raw_Part_v_Part"       # unused today — plex-etl-sales-orders runs sales_orders.yaml instead, see below
plex_host      = "vox.test.odbc.plex.com"
plex_odbc_user = "edominguez.parasol"
image_url      = "us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest"  # bootstrap only — pin to a commit SHA once you push a real build, never leave this as :latest long-term
```

> `bq_table`/`plex_view` only take effect if `report_config_gcs_path` is
> empty. `terraform.tfvars.example` already sets it to
> `gs://voxdatalake-report-configs/reports/sales_orders.yaml` — so unless
> you deliberately blank that out, `plex-etl-sales-orders` runs the Sales Orders
> pipeline (27 Plex views) regardless of what `bq_table`/`plex_view` say.

> **Fix the Sales Orders names the example still carries.**
> `terraform.tfvars.example` sets `cloud_run_job = "plex-etl"`,
> `cloud_run_job_test = "plex-etl-test"`, `scheduler_job = "plex-daily-sync"`
> and `scheduler_job_test = "plex-daily-sync-test"` — the names retired on
> 2026-09-04. Delete those four lines (the `variables.tf` defaults are the
> current names: `plex-etl-sales-orders`, `plex-etl-sales-orders-test`,
> `plex-sales-orders-sync`, `plex-sales-orders-sync-test`), or every command
> below naming those jobs will fail with NOT_FOUND.

### Step 9 · Create the GCP infrastructure

Still in the `terraform/` folder, initialise, then deploy from the repo root:

```bash
terraform init
cd ..
./scripts/deploy.sh     # plan → review → type the change count → apply exactly that plan
```

`deploy.sh` is the only way this project applies Terraform, including the
first time. Terraform itself runs a **deploy guard** (`scripts/tf_guard.py`,
called from `terraform/main.tf`) on every plan and apply: it refuses unless
this is the primary clone (not a `git worktree`), on `main`, with a clean
working tree, and `main` equal to `origin/main` — so what gets deployed is
always what GitHub shows. A fresh clone of `main` passes. It needs `python` on
your `PATH` and Git Bash to run `deploy.sh`.

**This creates the entire 13-pipeline, 26-job stack in one pass** — `terraform/main.tf` defines all 26 `google_cloud_run_v2_job` resources with no conditional gating, not just `plex-etl-sales-orders`. Takes **2–5 minutes**. Among what it creates:
- A service account (the "identity" every Cloud Run job uses)
- `PlexProd`/`PlexTest` BigQuery datasets and their `sync_metadata` tables (`job_run_log` is created by the job itself on its first run)
- Every `reports/` YAML and SQL file, uploaded to the report-configs bucket
- An Artifact Registry repository (where your Docker image lives)
- **Five** Secret Manager secrets (empty containers — you'll fill in the IAM token next step): `plex-access-token`, `sendgrid-api-key`, `plex-odbc-user`, `plex-odbc-password`, `plex-company-code`
- All 26 Cloud Run job definitions (13 pipelines × prod/test)
- All 52 Cloud Scheduler jobs — one daily trigger + one 9:45 PM Mountain retry trigger per Cloud Run job

**Check it worked:** In GCP Console → **Secret Manager**, you should see 5 secrets listed.

> **If you see errors:** See [DEPLOYMENT_GUIDE.md Step 1.4](DEPLOYMENT_GUIDE.md#14-if-resources-already-exist-state-recovery) for how to recover from state issues. Cloud Run jobs failing with "image not found" is expected until Step 11.

### Step 10 · Store your Plex token in Secret Manager

The token lives in a `.env` file locally. For GCP, it goes into Secret Manager — a secure vault that Cloud Run can read at runtime. Copy the token from your `.env` file:

```bash
echo -n '<paste-your-PLEX_ACCESS_TOKEN-value-here>' | \
  gcloud secrets versions add plex-access-token --data-file=- --project=voxdatalake
```

**Check it worked:**
```bash
gcloud secrets versions list plex-access-token --project=voxdatalake
# Should show version 1 with state "enabled"
```

### Step 11 · Build and push the Docker image to GCP

```bash
# Run from the repo root (not terraform/)

# Allow Docker to push to your GCP registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Tag with the current commit SHA — never ":latest" for anything deployed
SHA=$(git rev-parse --short HEAD)
docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA \
             -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest .

# Push both tags (this uploads the image to GCP — takes 3–8 minutes first time)
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest
```

Set `image_url` in `terraform.tfvars` to that `:$SHA` tag and deploy again — this is what actually creates `plex-etl-sales-orders` (and the other 25 jobs) on a real image:

```bash
./scripts/deploy.sh
```

**This is the only time in this walkthrough that a Terraform apply moves an image onto a job.** Every job has `lifecycle { ignore_changes = [image] }` specifically so a *later* apply (for something unrelated) can never silently swap the image out. On any later rebuild, pushing a new image does nothing by itself — run `./scripts/deploy_preflight.sh`, then `deploy/cloudbuild.yaml` (`gcloud builds submit --config deploy/cloudbuild.yaml --project=voxdatalake --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .`), whose `deploy-all` step moves all 26 jobs from one build.

### Step 12 · Run the job manually to test

```bash
gcloud run jobs execute plex-etl-sales-orders --region=us-central1 --project=voxdatalake --wait
```

This runs the exact same job that will run automatically every day. `--wait` keeps your terminal open and shows you the exit status.

**Check the logs:**
```bash
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl-sales-orders" \
  --project=voxdatalake \
  --limit=30 \
  --format="table(timestamp,textPayload)"
```

Or in GCP Console: **Cloud Run** → **Jobs** → `plex-etl-sales-orders` → click the execution → **Logs** tab.

### Step 13 · Verify data is in BigQuery

`plex-etl-sales-orders` runs the Sales Orders pipeline (see the note under Step 8) and writes to the dataset `bq_dataset` names (`PlexTest` in the Step 8 example), so look for its report tables, not just `raw_Part_v_Part`:

In GCP Console: **BigQuery** → `voxdatalake` → `PlexTest` → `raw_Sales_v_PO` → **Preview** tab. You should also see `sales_orders_report`, `sales_orders_open_report` and the pipeline's other views. Query one to be sure — a job can exit 0 while view creation failed:

```bash
bq query --use_legacy_sql=false --project_id=voxdatalake \
  "SELECT COUNT(*) FROM \`voxdatalake.PlexTest.sales_orders_report\`"
```

---

## You're done

`plex-etl-sales-orders` (Sales Orders) now runs daily at 7:00 PM Mountain; `plex-etl-sales-orders-test` at 7:10 PM Mountain (with the live `terraform.tfvars`; the `variables.tf` defaults are 02:00/03:00 UTC). The other 24 jobs Step 9 created run on their own schedules — full list in [docs/EMAIL_SCHEDULE.md](EMAIL_SCHEDULE.md). You don't need to do anything else.

**To check on a specific day's run:** GCP Console → **Cloud Run** → **Jobs** → `plex-etl-sales-orders` (or any other job) → **Executions** tab shows each run with its status.

**If a run fails:** `max_retries` on the job itself is 1, not 3 — the real safety net is a separate scheduler that fires at 9:45 PM Mountain (`RUN_MODE=retry`) and re-runs the job only if today's scheduled run didn't already succeed. Check the logs for the original error. See [DEPLOYMENT_GUIDE.md Troubleshooting](DEPLOYMENT_GUIDE.md#troubleshooting) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common fixes.

**To make changes:** every change goes through a `dev*` branch and `main` (`CONTRIBUTING.md`). A code change (`main.py`) ships as an image: `./scripts/deploy_preflight.sh`, then the `gcloud builds submit` command in Step 11's note — pushing an image alone does nothing. A report change (YAML/SQL) or `terraform.tfvars` change ships with `./scripts/deploy.sh`. See [OPERATIONS.md](OPERATIONS.md).

---

## Quick reference: most-used commands

```bash
# Run the job manually (any job: plex-etl-<pipeline>[-test])
gcloud run jobs execute plex-etl-sales-orders --region=us-central1 --project=voxdatalake --wait

# Check recent logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl-sales-orders" \
  --project=voxdatalake --limit=20 --format="table(timestamp,textPayload)"

# Rotate the Plex token
echo -n 'NEW_TOKEN' | gcloud secrets versions add plex-access-token \
  --data-file=- --project=voxdatalake

# Pause the daily schedule (keeps everything deployed, just stops auto-runs).
# Its -retry scheduler (plex-sales-orders-sync-retry) fires separately — pause it too.
gcloud scheduler jobs pause plex-sales-orders-sync --location=us-central1 --project=voxdatalake

# Resume the schedule
gcloud scheduler jobs resume plex-sales-orders-sync --location=us-central1 --project=voxdatalake
```

For the full command reference, see [docs/API_REFERENCE.md](API_REFERENCE.md).
