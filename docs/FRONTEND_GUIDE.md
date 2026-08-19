# Frontend Developer's Guide to the Plex → BigQuery Pipeline

> Written for developers comfortable with JavaScript, APIs, and the browser — but new to backend infrastructure, cloud deployments, and databases. Every concept has a frontend analogy. Use this to understand *why* the system works the way it does, and the second half as a step-by-step guide to build it from scratch.

---

## The problem we're solving

Vox Nutrition uses **Plex ERP** to manage manufacturing: parts, orders, inventory, shipping. The data lives in Plex's database, but Plex's reporting UI is slow and limited.

The goal: copy that data into **BigQuery** on a nightly schedule so the data team can query it with SQL, build dashboards, and do analysis — without clicking around in Plex.

Plex exposes data through **ODBC** (an older database connection standard, like using `pg` or `mysql2` in Node.js). So the pipeline: **connects via ODBC → pulls data → loads it into BigQuery every night.**

---

## The big picture

```mermaid
graph TD
    subgraph "Every night — automated"
        CS[⏰ Cloud Scheduler\n7:00 PM Mountain daily]
    end

    subgraph "Google Cloud — voxdatalake"
        CS -->|HTTP trigger| CRJ[📦 Cloud Run Job\nplex-etl]
        CRJ -->|reads config| GCS[☁ Cloud Storage\nvoxdatalake-report-configs]
        CRJ -->|reads secret| SM[🔑 Secret Manager\nplex-access-token]
        SA[🪪 Service Account\nplex-etl-sa] -->|identity for| CRJ
        CRJ -->|writes 13 raw tables| BQ[(📊 BigQuery\nPlexProd dataset)]
        CRJ -->|creates JOIN views| VIEW[(📊 sales_orders_report +\nsales_orders_open_report)]
    end

    subgraph "Plex ERP — external"
        CRJ -->|ODBC over TCP :19995| PLEX[🏭 vox.odbc.plex.com]
    end
```

**Every arrow is a network call.** The Cloud Run job is a single Python script that makes all of them in sequence.

**This diagram is one report family (Sales Orders / `plex-etl`) as a
worked example** — the same shape repeats 8 times (16 jobs total, prod +
test), each with its own schedule and its own `Cloud Run Job` box reading
its own YAML from the same `voxdatalake-report-configs` bucket. Not
pictured: the daily scheduler shown here has a sibling 9:45 PM Mountain retry
scheduler on every job, and `CRJ -->|creates JOIN views|` can fan out to
several named reports from one job (Sales Orders → 9, Work Orders → 4),
not always exactly one.

---

## Frontend analogies for every concept

### Docker = a `node_modules` folder that ships with the app

When you run a Node.js app, you need `node_modules`. Docker packages your code + ALL dependencies (Python runtime, system libraries, the Plex ODBC driver binary) into a single portable image. Anyone with Docker can run it identically.

```
Your app code
+ Python 3.11
+ pip packages (pyodbc, pandas, google-cloud-bigquery, PyYAML)
+ Linux system packages (unixODBC)
+ Plex ODBC driver (.so files)
= One Docker image — runs the same everywhere
```

The `Dockerfile` is like a `package.json` + a `postinstall` script that sets up the whole environment.

### Cloud Run Job = a Lambda / Vercel function on a cron

Cloud Run runs your Docker container on demand — no server sitting idle. A **Job** (vs a Service) runs once, does its work, and exits.

```
Vercel:    deploy function → runs on HTTP request → exits
Cloud Run: deploy container → runs on trigger     → exits
```

Cloud Scheduler is the trigger — it fires an HTTP POST to Cloud Run at 7:00 PM Mountain, like a GitHub Actions schedule.

### BigQuery = Supabase for analytics

BigQuery is a SQL database optimized for reading massive amounts of data (analytics), not high-frequency writes (transactions):
- Reading 10 million rows is fast and cheap
- You overwrite whole tables, not individual rows
- It's for batch analysis and dashboards, not live frontend queries

### Secret Manager = `.env` but encrypted and managed by GCP

Your `.env` holds secrets locally. In production, you can't use `.env` — it doesn't exist inside a Docker container running on GCP servers.

```
Local:      PLEX_ACCESS_TOKEN=abc123  (in .env file)
Production: PLEX_ACCESS_TOKEN → read from Secret Manager at startup
```

### Cloud Storage (GCS) = S3 / a CDN but for config files

Report definitions (which Plex views to query, what SQL to run in BigQuery) live in GCS as YAML and SQL files. The container downloads them at startup. Edit a file in GCS → next run picks it up. No code change, no deployment.

```
Old way:  change a query → edit code → rebuild Docker → redeploy
New way:  change a query → edit YAML in GCS Console → trigger job
```

### Terraform = `npm install` for cloud infrastructure

You describe what GCP resources you want in `.tf` files. `terraform apply` creates them.

```
package.json     →  terraform/*.tf
npm install      →  terraform apply
node_modules/    →  actual GCP resources (Service Account, BigQuery, Cloud Run...)
```

Delete a line from `.tf` → `terraform apply` deletes the resource. Add a line → it creates it.

### Service Account = an API key your app authenticates with

Cloud Run needs a GCP identity to call GCP APIs (BigQuery, Secret Manager). A Service Account is a non-human identity: `plex-etl-sa@voxdatalake.iam.gserviceaccount.com`. Terraform creates it and grants it exactly the permissions the job needs.

```
Your frontend:  uses VITE_SUPABASE_KEY, VITE_API_KEY, etc.
Cloud Run:      uses a Service Account (managed by GCP automatically)
```

### ODBC = a database driver

ODBC is a standard protocol for connecting to databases — equivalent to `npm install pg` (the Node.js Postgres driver), except it's a C-level binary that Python loads.

```
Node.js + Postgres:   npm install pg   → import {Client} from 'pg'
Python + Plex:        DataDirect .so   → import pyodbc
```

### IAM token = a long-lived API key

Plex uses a token-based auth system for ODBC connections. You generate a token from your Plex user account and pass it on each connection. Unlike OAuth tokens, **this token does not expire** — it's permanently valid until you replace it.

```
Web auth:   POST /login → { token: "eyJ..." } → Authorization: Bearer eyJ...
Plex ODBC:  token from Plex portal → CustomProperties=authmethod=iam; accesstoken=NTI...
```

---

## How data flows during a run

```mermaid
sequenceDiagram
    participant SCHED as ⏰ Scheduler
    participant CR as 📦 Cloud Run Job
    participant GCS as ☁ Cloud Storage
    participant SM as 🔑 Secret Manager
    participant PLEX as 🏭 Plex ODBC
    participant BQ as 📊 BigQuery

    SCHED->>CR: POST /jobs/plex-etl:run
    Note over CR: Container starts, main.py runs
    CR->>SM: GET plex-access-token
    SM-->>CR: token string
    CR->>GCS: GET reports/sales_orders.yaml
    GCS-->>CR: 13 extractions + bq_view config
    CR->>PLEX: ODBC connect (driver-direct)<br/>HOST=vox.odbc.plex.com:19995<br/>UID=edominguez.parasol<br/>authmethod=iam; accesstoken=...
    PLEX-->>CR: connection established

    loop For each of 13 Plex views
        CR->>PLEX: SELECT * FROM {view}
        PLEX-->>CR: rows as DataFrame
        CR->>BQ: WRITE_TRUNCATE → raw_{view}
        CR->>BQ: UPDATE sync_metadata
    end

    CR->>GCS: GET sql/sales_orders_view.sql
    GCS-->>CR: JOIN SQL
    CR->>BQ: CREATE OR REPLACE VIEW sales_orders_report
    Note over CR: Container exits, email sent
```

---

## The multi-report config system

The biggest architectural decision: **report definitions don't live in the code**. They live in Cloud Storage as YAML files.

```
gs://voxdatalake-report-configs/
├── reports/
│   ├── sales_orders.yaml      ← prod: which 13 views to extract (shown below)
│   └── ... 7 more report families (work_orders, purchasing_open_orders,
│           part_obsolescence, inventory_activity, inventory_snapshot,
│           quality_nonconformance, part_on_hand_inventory)
├── test/
│   └── sales_orders.yaml      ← test: same views → PlexTest dataset (+ the other 7)
└── sql/
    └── sales_orders_view.sql  ← BigQuery JOIN view — the actual report SQL
```

Sales Orders is one of **8 report families** (16 Cloud Run jobs total, prod+test) — used here as the running example because it's the original pipeline, not because it's the only one.

The Cloud Run job reads the YAML at startup on every execution. To change a query: edit the file in GCS and trigger the job. No container rebuild, no Terraform apply.

**The `REPORT_CONFIG_GCS_PATH` env var** tells the container which YAML to load — pointing a different job at a different YAML is how 16 jobs share one Docker image. It's not the *only* difference between a prod and test job, though (see the diagram below — `PLEX_HOST` and the BigQuery dataset differ too); it's the one that decides *what gets extracted*, which is this section's point.

---

## Prod vs test environments

```mermaid
graph LR
    GCS["gs://voxdatalake-report-configs"]

    subgraph PROD["🟢 Production"]
        PJ["Cloud Run Job: plex-etl\nScheduler: 7:00 PM Mountain"]
        PH["vox.odbc.plex.com ✅"]
        PD["BigQuery: PlexProd"]
        PJ -->|ODBC| PH
        PJ -->|writes| PD
    end

    subgraph TEST["🔵 Test"]
        TJ["Cloud Run Job: plex-etl-test\nScheduler: 7:10 PM Mountain"]
        TH["vox.test.odbc.plex.com ✅"]
        TD["BigQuery: PlexTest"]
        TJ -->|ODBC| TH
        TJ -->|writes| TD
    end

    GCS -->|"reports/sales_orders.yaml"| PJ
    GCS -->|"test/sales_orders.yaml"| TJ
```

Same container image, same GCS bucket, different ODBC host and BigQuery dataset. Both use the same IAM token — it works on both endpoints.

This diagram shows one report family (Sales Orders) — the other 7 follow the identical prod/test pattern, just with their own job names, schedules, and `REPORT_CONFIG_GCS_PATH`. Every job here also has a **third** scheduler not pictured: a shared 9:45 PM Mountain retry trigger (`RUN_MODE=retry`) that only actually re-runs the job if today's regular scheduled run failed — see `docs/EMAIL_SCHEDULE.md` for the full 16-job/32-scheduler picture.

---

## Authentication: two separate systems

```mermaid
graph TD
    subgraph "Who is Cloud Run talking to Plex as?"
        TOKEN["Plex IAM Token<br/>stored in Secret Manager<br/>does not expire"] -->|authenticates to| PLEX_AUTH["Plex ODBC server<br/>edominguez.parasol"]
    end

    subgraph "Who is Cloud Run talking to GCP as?"
        SA["GCP Service Account<br/>plex-etl-sa@voxdatalake"] -->|authenticates to| GCP["Secret Manager<br/>BigQuery<br/>Cloud Storage"]
    end
```

| | Plex IAM Token | GCP Service Account |
|---|---|---|
| **Authenticates to** | Plex ODBC endpoint | GCP services |
| **Where it lives** | Secret Manager (you stored it) | Managed by GCP automatically |
| **Expires?** | No — permanent until replaced | Rotated by GCP transparently |
| **Where to get it** | Plex portal → user profile → API Access | Created by Terraform |

---

## The ODBC connection string explained

```python
# What you're used to (Postgres URL):
"postgresql://user:password@host:5432/dbname"

# What Plex ODBC looks like (driver-direct):
"DRIVER={/usr/oaodbc81/lib64/ivoa27.so};"
"HOST=vox.odbc.plex.com;"
"PORT=19995;"
"ServerDataSource=ReportDataSource;"
"Encrypted=1;"
"UseLDAP=0;"
"UID=edominguez.parasol;"
"PWD=;"
"CustomProperties=authmethod=iam; accesstoken=NTIx..."
```

| Part | Meaning |
|---|---|
| `DRIVER={...}` | Path to the driver binary — like `require('./driver.so')` |
| `HOST=` | Plex ODBC server (`vox.odbc.plex.com` prod, `vox.test.odbc.plex.com` test) |
| `PORT=19995` | Plex always uses this port |
| `ServerDataSource=ReportDataSource` | Named data service on the Plex server |
| `Encrypted=1` | TLS — like `https` vs `http` |
| `UID=edominguez.parasol` | Plex login: `username.company` format |
| `PWD=` | Empty — IAM token auth, no password |
| `CustomProperties=...` | **Must be last** — contains semicolons that would confuse the parser if in the middle |

**Why driver-direct, not DSN?** The DSN config (`/etc/odbc.ini`) works for basic connections but unixODBC drops driver-specific attributes like `CustomProperties` when routing through a DSN. IAM auth requires `CustomProperties`, so we bypass the DSN entirely and pass all attributes directly.

---

## What each file does

| File | Frontend equivalent | What it does |
|---|---|---|
| `main.py` | `server.js` / route handler | Orchestrates the ETL: load GCS config, connect ODBC, loop extractions, write BigQuery, create VIEW |
| `email_utils.py` | notification service | Sends HTML run summary via SendGrid |
| `Dockerfile` | `package.json` + setup script | Defines the container: Python, ODBC driver, pip packages |
| `docker-compose.yml` | `vite.config.js` for local dev | Local runner — forces `OUTPUT_MODE=local`, mounts `./output/` |
| `.env` | `.env.local` | Local secrets — never committed |
| `reports/sales_orders.yaml` | feature flag config | Which 13 Plex views to extract, and — since `bq_view` can be a list — its `category`/`display_name` fields and which named report(s) get built from them. Today it actually produces **two** peer reports (`sales_orders_report` + `sales_orders_open_report`) from the same 13-view extraction, not one. |
| `reports/sql/sales_orders_view.sql` | a database migration | The BigQuery JOIN SQL that produces the 16-field report — its sibling `sales_orders_open_view.sql` produces the second one from the same raw tables |
| `config/odbcinst.ini` | driver registration | Tells unixODBC where the Plex driver binary lives |
| `terraform/main.tf` | infrastructure definition | All GCP resources: Service Account, BigQuery, Cloud Run, Scheduler, GCS bucket |
| `terraform/terraform.tfvars` | `.env` for Terraform | Your project-specific values — gitignored, never committed |

---

## What requires a rebuild vs. what doesn't

```mermaid
flowchart TD
    change[You made a change] --> q1{Where is the change?}
    q1 -->|YAML or SQL in GCS| gcs["gcloud storage cp → trigger job\nNo code change, no deployment"]
    q1 -->|terraform.tfvars| apply["terraform apply\n~30 seconds"]
    q1 -->|.py file, Dockerfile, requirements.txt| rebuild["docker build + push a SHA tag,\nTHEN explicitly gcloud run jobs update --image=...\n(or deploy-all in cloudbuild.yaml)\n3–8 minutes"]
```

**Only `gcloud storage cp` + trigger** (seconds, no deployment):
- Which Plex views to extract (`reports/*.yaml`)
- Filters, date columns on any view
- BigQuery JOIN view SQL (`reports/sql/*.sql`)
- A report's `category`/`display_name` (controls the email subject/body)

**Only `terraform apply`** (30 seconds, no code change):
- ODBC host, port, ServerDataSource
- BigQuery table or dataset name
- Email on/off, sender, recipients
- Cron schedule for a specific job

**Needs Docker rebuild — AND an explicit redeploy** (3–8 min build, plus one more step people miss):
- `main.py`, `email_utils.py` — logic changes
- `templates/report.html` — email design
- `requirements.txt` — new Python package
- `driver/` — Plex ODBC driver update

**The step people miss:** `docker push` does not update any running job by
itself — not "at the next execution," not via `terraform apply`. Every
`google_cloud_run_v2_job` has `lifecycle { ignore_changes = [image, ...] }`
specifically so a routine `apply` can never silently swap a job's image.
The image only moves when something explicitly says so:
```bash
gcloud run jobs update JOB_NAME --image=us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA --region=us-central1
```
or run `deploy/cloudbuild.yaml`'s `deploy-all` step, which loops this over
all 16 jobs from one build. Always tag with the commit SHA, never
`:latest` — `:latest` is still pushed for manual `docker pull`
convenience, but nothing deployed ever reads it.

---

## Build from scratch — complete setup guide

Use this if you're setting up the pipeline in a new GCP project or rebuilding after a teardown.

### Prerequisites

- GCP project created with billing enabled
- `gcloud` CLI installed and authenticated: `gcloud auth login`
- `terraform` CLI ≥ 1.5 installed
- `docker` CLI installed and running
- Plex ODBC driver files in `driver/` (contact Plex support for the Linux `.tar.gz`)
- Plex IAM token (from Plex portal → your profile → API Access)
- SendGrid account + verified sender address (optional, for email reports)

### Phase 1 — Validate locally before touching GCP

```bash
# 1. Copy and fill in credentials
cp .env.example .env
# Edit .env:
#   PLEX_HOST=vox.test.odbc.plex.com
#   PLEX_ODBC_USER=yourname.company
#   PLEX_ACCESS_TOKEN=your-plex-token
#   BQ_DATASET=PlexTest
#   GCP_PROJECT=your-gcp-project

# 2. Build and run locally — writes CSVs to ./output/
docker compose build
docker compose up

# 3. Inspect output
ls output/
# Should see files like raw_Sales_v_PO_20260701T020000Z.csv
```

If you see data in `./output/` the ODBC connection and extraction are working. Move to Phase 2.

### Phase 2 — Deploy to GCP

```bash
# 1. Authenticate Docker to Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# 2. Copy and fill in Terraform variables
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — fill in gcp_project, plex_host, plex_odbc_user,
# image_url, email settings, etc.

# 3. Init and apply — creates all GCP infrastructure
terraform init
terraform apply -var-file=terraform.tfvars
# Type 'yes' when prompted. Takes ~2 minutes on first run.

# 4. Build and push the container image — tag with the commit SHA, never
# ":latest" (nothing deployed ever reads that tag; see step 4b for why)
cd ..
SHA=$(git rev-parse --short HEAD)
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT/plex-pipeline/etl:$SHA \
             -t us-central1-docker.pkg.dev/YOUR_PROJECT/plex-pipeline/etl:latest .
docker push us-central1-docker.pkg.dev/YOUR_PROJECT/plex-pipeline/etl:$SHA
docker push us-central1-docker.pkg.dev/YOUR_PROJECT/plex-pipeline/etl:latest

# 4b. Set image_url in terraform.tfvars to that :$SHA tag and re-apply —
# this is what actually creates the job on a real image (only works
# because it doesn't exist yet; every job's lifecycle.ignore_changes means
# a LATER rebuild needs an explicit `gcloud run jobs update` instead, not
# another `terraform apply`):
cd terraform && terraform apply -var-file=terraform.tfvars && cd ..

# 5. Store the Plex IAM token in Secret Manager
echo -n 'YOUR_PLEX_TOKEN' | \
  gcloud secrets versions add plex-access-token \
  --data-file=- --project=YOUR_PROJECT

# 6. Upload report configs to GCS — BOTH sql files, not just one, since
# sales_orders.yaml's bq_view is a list producing two peer reports
gcloud storage cp reports/sales_orders.yaml \
  gs://YOUR_PROJECT-report-configs/reports/
gcloud storage cp reports/test/sales_orders.yaml \
  gs://YOUR_PROJECT-report-configs/test/
gcloud storage cp reports/sql/sales_orders_view.sql \
  gs://YOUR_PROJECT-report-configs/sql/
gcloud storage cp reports/sql/sales_orders_open_view.sql \
  gs://YOUR_PROJECT-report-configs/sql/

# 7. Trigger the test job and watch it run
gcloud run jobs execute plex-etl-test \
  --region=us-central1 --project=YOUR_PROJECT --wait
```

This walks through just `plex-etl`/`sales_orders` — a real from-scratch
deploy creates all 16 jobs at once in step 3 (no per-job gating in
`terraform/main.tf`), so you'd repeat steps 6-7 for the other 7 report
families too before trusting the whole stack.

### Phase 3 — Validate

```bash
# Check all 13 raw tables exist with data
bq query --nouse_legacy_sql --project=YOUR_PROJECT \
  "SELECT table_name, row_count
   FROM YOUR_PROJECT.PlexTest.INFORMATION_SCHEMA.PARTITIONS
   ORDER BY table_name"

# Preview the 16-field report view
bq query --nouse_legacy_sql --project=YOUR_PROJECT \
  "SELECT * FROM \`YOUR_PROJECT.PlexTest.sales_orders_report\` LIMIT 10"
```

If the view returns rows with correct data, Phase 3 is done. Repeat Phase 2 step 7 with `plex-etl` (prod job) to go live.

---

## Email behavior

The job sends a SendGrid email after every run with this logic:

| Attempt | Outcome | Email sent? |
|---|---|---|
| First (attempt 0) | Success or failure | ✅ Always — you know the job ran |
| Retry (attempt 1+) | Failure | ❌ Suppressed — no inbox spam |
| Retry (attempt 1+) | Success | ✅ Always — you know it recovered |

Cloud Run injects `CLOUD_RUN_TASK_ATTEMPT` (0-indexed) into every container execution. `max_retries = 1` means at most one retry after a failure.

---

## Common errors

| Error | Plain English | Fix |
|---|---|---|
| `HY000 10300: access token invalid` | The IAM token in Secret Manager is wrong | Replace it with the correct Plex token via `gcloud secrets versions add` |
| `HY000 3059: data source not defined` | DSN-based auth was used instead of driver-direct | Ensure `PLEX_ACCESS_TOKEN` is set — IAM auth uses driver-direct, not the DSN |
| `403: Policy update access denied` | Your GCP account isn't a project owner | Ask a GCP admin for `roles/owner` on the project |
| `409: Already Exists` in Terraform | Resource exists in GCP but not in Terraform state | Import it: `terraform import <resource> <id>` |
| `Secret not found` in Cloud Run | Secret version not created yet | Run `gcloud secrets versions add plex-access-token ...` |
| `BigQuery view error: column not found` | Column name in SQL doesn't match actual Plex schema | Query `INFORMATION_SCHEMA.COLUMNS` on the raw table to get real names |

---

## GCP services and IAM summary

| GCP Service | What it does in this pipeline |
|---|---|
| **Cloud Run Jobs** | Runs the Python container on schedule or manual trigger — 16 jobs total (8 report families × prod/test), all sharing one image |
| **Cloud Scheduler** | Fires HTTP POST to Cloud Run — `plex-etl` at 7:00 PM Mountain (prod) / 7:10 PM Mountain (test) as the running example, staggered 10 minutes apart through 9:30 PM Mountain across all 8 families, each job also with its own retry trigger firing together at 9:45 PM Mountain (32 scheduler jobs total) |
| **BigQuery** | Stores dozens of raw Plex tables across `PlexProd`/`PlexTest` + one or more named JOIN views per report family (`sales_orders_report` + `sales_orders_open_report` for this one) |
| **Cloud Storage** | Holds YAML report configs and SQL view definitions — editable at runtime |
| **Secret Manager** | Stores the Plex IAM token and SendGrid API key |
| **Artifact Registry** | Private Docker registry — stores the ETL container image |
| **IAM / Service Accounts** | `plex-etl-sa@voxdatalake` runs the job with least-privilege access |

**IAM roles granted to `plex-etl-sa`:**

| Role | Why |
|---|---|
| `roles/bigquery.dataEditor` | Write rows to BigQuery |
| `roles/bigquery.jobUser` | Run BigQuery load jobs |
| `roles/secretmanager.secretAccessor` | Read Plex token from Secret Manager |
| `roles/artifactregistry.reader` | Pull the Docker image |
| `roles/storage.objectViewer` | Read YAML/SQL configs from GCS |
| `roles/run.invoker` | Cloud Scheduler invokes Cloud Run |

---

## Glossary

| Term | Definition |
|---|---|
| **ETL** | Extract, Transform, Load — pull data from Plex (extract), reshape it (transform), load to BigQuery |
| **ELT** | Extract, Load, Transform — this pipeline's actual pattern: raw data lands in BigQuery first, then the VIEW transforms it via SQL |
| **ODBC** | Open Database Connectivity — a standard database driver interface. Like a universal adapter for databases |
| **DSN** | Data Source Name — a named ODBC connection config in `/etc/odbc.ini`. We bypass it for IAM auth (driver-direct) |
| **IAM** | Identity and Access Management — controls who can do what. Used by both GCP and Plex |
| **Service Account** | A GCP identity for a machine/app (not a human) |
| **BigQuery** | Google's managed data warehouse. SQL-queryable, handles massive datasets, optimized for analytics |
| **Cloud Run** | GCP's serverless container platform |
| **Cloud Scheduler** | GCP's managed cron service |
| **Artifact Registry** | GCP's private Docker registry |
| **Secret Manager** | GCP's encrypted secrets store |
| **Terraform** | Infrastructure-as-code tool — defines GCP resources in `.tf` files |
| **WRITE_TRUNCATE** | BigQuery write mode: delete and replace the entire table. Used for full-refresh (all 13 views) |
| **DataDirect OpenAccess SDK** | The Plex ODBC driver — a C binary (`.so`) that speaks Plex's proprietary ODBC protocol |
