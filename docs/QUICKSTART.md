# Quick Start Guide

> **Who is this for?** Anyone setting up this pipeline for the first time with no prior knowledge of Docker, GCP, or ETL assumed. Every step tells you what you're doing and why, not just the commands to type.

---

## What are we building?

A pipeline that automatically pulls parts data from **Plex ERP** and stores it in **Google BigQuery** every morning at 2 AM. Once set up, it runs on its own forever — you don't touch it again unless something needs to change.

There are two phases:
1. **Local test** — get the data pull working on your laptop (proves the connection works before deploying anything to the cloud)
2. **Cloud deploy** — move it to Google Cloud so it runs automatically on a schedule

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

### Things to get from Plex support (request these early, may take a day or two)

- [ ] **Plex ODBC credentials:** username, password, CompanyCode
- [ ] **Linux ODBC driver files:** a `.zip` or `.tar` file containing the driver
- [ ] **IAM access token** for ODBC authentication (ask for IAM/token-based auth)
- [ ] **Confirmation of** the view name, column names, and whether you have read access

Use [PLEX_SUPPORT_TEMPLATE.md](../PLEX_SUPPORT_TEMPLATE.md) as your email template.

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

The Plex ODBC driver is a set of Linux binary files that the Docker container uses to talk to Plex. You get these from Plex support — they come as a `.zip` or `.tar` archive.

Create a `driver/` folder in the repo root and extract the files there. When done, you should have:

```
driver/
  lib64/
    ivoa27.so       ← this file must exist
    ddtrc27.so
  etc/
    lang/
      usenglish.msg
```

If Plex gave you a `.tar` file inside the archive called `ivoaLinux64.tar`, extract it:

```bash
tar -xf driver/etc/tar/ivoaLinux64.tar -C driver/ lib64/
```

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
bq_table       = "raw_Part_v_Part"
plex_host      = "vox.test.odbc.plex.com"
plex_odbc_user = "edominguez.parasol"
image_url      = "us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest"
```

### Step 9 · Create the GCP infrastructure

Still in the `terraform/` folder:

```bash
terraform init
terraform apply -var-file=terraform.tfvars
```

Type `yes` when it asks. This takes **2–5 minutes** and creates:
- A service account (the "identity" Cloud Run uses)
- BigQuery dataset and metadata table
- An Artifact Registry repository (where your Docker image lives)
- Four Secret Manager secrets (empty containers — you'll fill one in the next step)
- A Cloud Run job definition
- A Cloud Scheduler cron job

**Check it worked:** In GCP Console → **Secret Manager**, you should see 4 secrets listed.

> **If you see errors:** See [DEPLOYMENT_GUIDE.md Step 1.4](../DEPLOYMENT_GUIDE.md) for how to recover from state issues.

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
# Go back to repo root (not terraform/)
cd ..

# Allow Docker to push to your GCP registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build
docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest .

# Push (this uploads the image to GCP — takes 3–8 minutes first time)
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest
```

Then re-run Terraform so it picks up the now-real image:

```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

### Step 12 · Run the job manually to test

```bash
gcloud run jobs execute plex-etl --region=us-central1 --project=voxdatalake --wait
```

This runs the exact same job that will run automatically every morning. `--wait` keeps your terminal open and shows you the exit status.

**Check the logs:**
```bash
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl" \
  --project=voxdatalake \
  --limit=30 \
  --format="table(timestamp,textPayload)"
```

Or in GCP Console: **Cloud Run** → **Jobs** → `plex-etl` → click the execution → **Logs** tab.

### Step 13 · Verify data is in BigQuery

In GCP Console: **BigQuery** → `voxdatalake` → `PlexTest` → `raw_Part_v_Part` → **Preview** tab.

You should see rows with part numbers, names, and statuses.

---

## You're done

The pipeline now runs automatically every morning at 2 AM UTC. You don't need to do anything else.

**To check on a specific day's run:** GCP Console → **Cloud Run** → **Jobs** → `plex-etl` → **Executions** tab shows each run with its status.

**If a run fails:** The job retries automatically up to 3 times. Check the logs for the error. See [DEPLOYMENT_GUIDE.md Troubleshooting](../DEPLOYMENT_GUIDE.md#troubleshooting) for common fixes.

**To make changes to the query or logic:** Edit `main.py`, rebuild and push the image (Step 11 again), no Terraform changes needed.

---

## Quick reference: most-used commands

```bash
# Run the job manually
gcloud run jobs execute plex-etl --region=us-central1 --project=voxdatalake --wait

# Check recent logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl" \
  --project=voxdatalake --limit=20 --format="table(timestamp,textPayload)"

# Rotate the Plex token
echo -n 'NEW_TOKEN' | gcloud secrets versions add plex-access-token \
  --data-file=- --project=voxdatalake

# Pause the daily schedule (keeps everything deployed, just stops auto-runs)
gcloud scheduler jobs pause plex-daily-sync --location=us-central1 --project=voxdatalake

# Resume the schedule
gcloud scheduler jobs resume plex-daily-sync --location=us-central1 --project=voxdatalake
```

For the full command reference, see [docs/API_REFERENCE.md](API_REFERENCE.md).
