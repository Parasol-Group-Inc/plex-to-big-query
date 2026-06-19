# Frontend Developer's Guide to the Plex → BigQuery Pipeline

> This guide is written for frontend developers who are comfortable with JavaScript, APIs, and the browser, but less familiar with backend infrastructure, databases, and cloud deployments. Every concept has a frontend analogy. Read this to understand *why* the system works the way it does.

---

## The problem we're solving

Parasol uses **Plex ERP** — an enterprise system that manages manufacturing: parts, orders, inventory, shipping. The data lives in Plex's database, but Plex's reporting UI is slow and limited.

We want to take that data and put it in **BigQuery**, where it can be queried fast, connected to dashboards, and used for analysis. But Plex doesn't have a REST API — it only exposes data through **ODBC**, which is an older database connection standard (think of it like a database driver, similar to how you'd use `pg` or `mysql2` in Node.js to connect to Postgres or MySQL).

So our job is to: **connect to Plex via ODBC, pull the data, and load it into BigQuery on a schedule.**

---

## The big picture

```mermaid
graph TD
    subgraph "Every morning at 2 AM UTC"
        CS[☁️ Cloud Scheduler\ncron: 0 2 * * *]
    end

    subgraph "Google Cloud — parasoldatalake"
        CS -->|HTTP trigger| CRJ[🏃 Cloud Run Job\nplex-etl]
        CRJ -->|reads secret| SM[🔐 Secret Manager\nplex-access-token]
        CRJ -->|pulls image from| AR[📦 Artifact Registry\nplex-pipeline/etl:latest]
        SA[🔑 Service Account\nplex-etl-sa] -->|identity for| CRJ
        CRJ -->|writes data| BQ[(📊 BigQuery\nplex_sandbox.\nraw_materials_parts)]
        CRJ -->|updates watermark| META[(📋 BigQuery\nplex_sandbox.\nsync_metadata)]
    end

    subgraph "Plex ERP — external"
        CRJ -->|ODBC over TCP :19995| PLEX[🏭 Plex ODBC Endpoint\nvox.odbc.plex.com]
    end
```

**Every arrow above is a network call.** The Cloud Run job is a single Python script that makes all of them in sequence.

---

## Frontend analogies for every concept

### Docker = a `node_modules` folder that ships with the app

When you run a Node.js app, you need the right `node_modules`. Docker packages your code + ALL its dependencies (the Python runtime, system libraries, the Plex ODBC driver binary) into a single portable image. Anyone with Docker can run it identically, no matter what OS they have.

```
Your app code
+ Python 3.11
+ pip packages (pyodbc, pandas, google-cloud-bigquery)
+ Linux system packages (unixODBC, libc6-i386)
+ Plex ODBC driver (.so files)
= One Docker image — runs the same everywhere
```

The `Dockerfile` is like a `package.json` + a `postinstall` script that sets up the whole environment.

### Cloud Run Job = a Lambda / Vercel serverless function on a cron

Cloud Run runs your Docker container on demand. There's no server sitting idle — GCP spins up a container, runs it, and shuts it down. A **Job** (as opposed to a Service) is specifically for one-off executions: it runs once, does its work, exits.

```
Vercel:    deploy function → runs when HTTP request arrives → exits
Cloud Run: deploy container → runs when triggered → exits
```

Cloud Scheduler is the trigger — it fires an HTTP POST to Cloud Run at 2 AM UTC every day, just like a GitHub Actions schedule triggers a workflow.

### BigQuery = Supabase for analytics

BigQuery is a SQL database, but optimized for reading massive amounts of data fast (analytics), not for high-frequency writes (transactions). Think of it like a Postgres database where:
- Reading 10 million rows is fast and cheap
- You can't update individual rows easily — you overwrite the whole table
- No live-updating frontend queries — it's for batch analysis and dashboards

### Secret Manager = `.env` but encrypted and managed by GCP

Your `.env` file holds secrets locally. In production, you can't use `.env` — you can't commit it, and it doesn't exist inside a Docker container running on someone else's servers.

Secret Manager is the cloud equivalent: secrets are stored encrypted, versioned, and access-controlled. Your Cloud Run job reads them at runtime via an API call.

```
Local:      PLEX_ACCESS_TOKEN=abc123  (in .env file)
Production: PLEX_ACCESS_TOKEN → read from Secret Manager at startup
```

### Terraform = `npm install` for cloud infrastructure

When you share a Node.js project, you don't commit `node_modules` — you commit `package.json` and run `npm install`. Infrastructure works the same way: you describe what you want in Terraform config files (`.tf`), and `terraform apply` creates it.

```
package.json     →  terraform/*.tf
npm install      →  terraform apply
node_modules/    →  actual GCP resources (Service Account, BigQuery, Cloud Run...)
```

If you delete a GCP resource and re-run `terraform apply`, it recreates it. If you delete a line from the `.tf` file and apply, it deletes the resource.

### Service Account = an API key your app authenticates with

When Cloud Run runs your container, it needs a Google identity to call GCP APIs (BigQuery, Secret Manager). It can't use your personal Google account — that would break when you change your password.

A Service Account is a non-human identity: `plex-etl-sa@parasoldatalake.iam.gserviceaccount.com`. Terraform creates it and grants it exactly the permissions the job needs: read secrets, write to BigQuery, pull Docker images.

```
Your frontend app:  uses API keys (VITE_SUPABASE_KEY, etc.)
Cloud Run:          uses a Service Account (managed by GCP, not you)
```

### ODBC = a database driver

ODBC (Open Database Connectivity) is a standard protocol for connecting to databases. It's the equivalent of `npm install pg` (the Node.js Postgres driver) — except ODBC is a C-level standard that works across languages, and Plex's version is a proprietary binary.

```
Node.js + Postgres:   npm install pg   → import {Client} from 'pg'
Python + Plex:        DataDirect driver → import pyodbc
```

The `.so` files in `driver/lib64/` are the equivalent of a compiled native addon — binary code that Python loads to speak the ODBC protocol.

### IAM token = a JWT / OAuth token

When you log into a web app, you get a JWT that proves your identity for subsequent API calls. Plex IAM tokens work the same way: you get a token from Plex, and each ODBC connection passes it in the `CustomProperties` field. Plex validates it and opens a connection as your user.

```
Web auth:   POST /login → { token: "eyJ..." } → Authorization: Bearer eyJ...
Plex ODBC:  token from Plex → CustomProperties=authmethod=iam; accesstoken=Mjc4...
```

---

## How data flows during a run

```mermaid
sequenceDiagram
    participant CS as Cloud Scheduler
    participant CR as Cloud Run Job
    participant SM as Secret Manager
    participant PLEX as Plex ERP
    participant BQ as BigQuery

    CS->>CR: HTTP POST (trigger)
    Note over CR: Container starts, main.py runs

    CR->>SM: GET plex-access-token (latest version)
    SM-->>CR: token string

    CR->>PLEX: ODBC connect (driver-direct)<br/>HOST=vox.odbc.plex.com:19995<br/>UID=edominguez.parasol<br/>CustomProperties=authmethod=iam; accesstoken=...
    PLEX-->>CR: connection established

    CR->>PLEX: SELECT * FROM Part_v_Part<br/>WHERE Part_Type = 'Raw Materials'<br/>ORDER BY Part_No ASC
    PLEX-->>CR: rows (pandas DataFrame)

    CR->>BQ: Load DataFrame (WRITE_TRUNCATE)<br/>→ parasoldatalake.plex_sandbox.raw_materials_parts
    BQ-->>CR: job complete, N rows written

    CR->>BQ: INSERT INTO sync_metadata<br/>(table_name, rows_written, synced_at)
    BQ-->>CR: ok

    Note over CR: Container exits, job marked complete
```

---

## Local mode vs cloud mode

The same Python script and Docker image runs in both modes. The difference is just where it reads credentials from and where it writes output.

```mermaid
graph LR
    subgraph "Local Mode  (docker compose up)"
        direction TB
        ENV[.env file<br/>on your laptop] --> DC[Docker container]
        DC -->|ODBC| PLEX_T[Plex test host<br/>vox.odbc.plex.com]
        DC -->|write| CSV["./output/*.csv<br/>on your laptop"]
    end

    subgraph "Cloud Mode  (Cloud Run job)"
        direction TB
        SM_C[Secret Manager<br/>plex-access-token] --> CRC[Cloud Run container]
        CRC -->|ODBC| PLEX_P[Plex host<br/>odbc.plex.com]
        CRC -->|write| BQ_C[BigQuery<br/>plex_sandbox.raw_materials_parts]
    end
```

Controlled by one env var: `OUTPUT_MODE=local` vs `OUTPUT_MODE=bigquery`. `docker-compose.yml` forces `local` so you can't accidentally write to prod BigQuery from your laptop.

---

## Authentication: two separate systems

There are two authentication systems at play. Beginners often confuse them.

```mermaid
graph TD
    subgraph "Who is Cloud Run talking to Plex as?"
        TOKEN[Plex IAM Token<br/>plex-access-token in Secret Manager] -->|proves identity to| PLEX_AUTH[Plex ERP ODBC server]
        NOTE1["User: edominguez.parasol<br/>Company: parasol"] -.-> PLEX_AUTH
    end

    subgraph "Who is Cloud Run talking to GCP as?"
        SA2[GCP Service Account<br/>plex-etl-sa@parasoldatalake] -->|proves identity to| GCP_SERVICES[Secret Manager<br/>BigQuery<br/>Artifact Registry]
        NOTE2["Managed automatically by GCP<br/>You never touch this token"] -.-> GCP_SERVICES
    end
```

| | Plex IAM Token | GCP Service Account |
|---|---|---|
| **Authenticates to** | Plex ERP ODBC endpoint | GCP services (BigQuery, Secret Manager) |
| **Where it lives** | Secret Manager (you put it there) | Managed by GCP automatically |
| **Who rotates it** | You, when Plex issues a new one | GCP (transparent to you) |
| **What happens if missing** | ODBC connection fails | Cloud Run can't read secrets or write to BQ |

---

## What each file does

```mermaid
graph LR
    subgraph "Python app (inside container)"
        M[main.py] -->|imports| EU[email_utils.py]
        M -->|reads| TMPL[templates/report.html]
    end

    subgraph "Container build"
        DF[Dockerfile] -->|installs| DRV[driver/lib64/*.so]
        DF -->|installs| REQ[requirements.txt]
        DF -->|copies| CFG[config/odbcinst.ini\nconfig/odbc.ini]
        DF -->|entry point| ENT[entrypoint.sh]
    end

    subgraph "Local run config"
        DC[docker-compose.yml] -->|mounts| OUTP[./output/]
        DC -->|loads| ENV[.env]
    end

    subgraph "GCP infrastructure"
        TF[terraform/main.tf] -->|defines| GCP[all GCP resources]
        TFVARS[terraform/terraform.tfvars] -->|configures| TF
    end
```

| File | Frontend equivalent | What it does |
|---|---|---|
| `main.py` | `server.js` / route handler | Orchestrates the whole ETL: fetch token, connect ODBC, query Plex, write BQ |
| `Dockerfile` | `package.json` + `Dockerfile` | Defines what goes in the container |
| `docker-compose.yml` | `vite.config.js` for local dev | Local runner config: mounts output folder, sets local-only env vars |
| `.env` | `.env.local` | Local secrets — never committed |
| `config/odbcinst.ini` | driver registration file | Tells the ODBC driver manager where the Plex driver binary lives |
| `config/odbc.ini` | database connection config | DSN definitions (PlexProduction, PlexTest) — hostname, port |
| `terraform/main.tf` | infrastructure-as-code | All GCP resources defined here — Service Account, BigQuery, Cloud Run, etc. |
| `terraform/terraform.tfvars` | `.env` for infrastructure | Your project-specific values for Terraform |

---

## The ODBC connection string explained

This is the most unusual part of the codebase — ODBC connection strings look weird if you've only seen database URLs.

```python
# What you're used to (Postgres URL):
"postgresql://user:password@host:5432/dbname"

# What Plex ODBC looks like:
"DRIVER={/usr/oaodbc81/lib64/ivoa27.so};" \
"HOST=vox.odbc.plex.com;" \
"PORT=19995;" \
"ServerDataSource=ReportDataSource;" \
"Encrypted=1;" \
"UseLDAP=0;" \
"UID=edominguez.parasol;" \
"PWD=;" \
"CustomProperties=authmethod=iam; accesstoken=Mjc4MDIy..."
```

Breaking it down:

| Part | Meaning |
|---|---|
| `DRIVER={...}` | Path to the driver binary — like `require('./driver.so')` |
| `HOST=` | The Plex ODBC server hostname |
| `PORT=19995` | Plex always uses port 19995 |
| `ServerDataSource=ReportDataSource` | Name of the data service on the Plex ODBC server |
| `Encrypted=1` | Use TLS (like `https` vs `http`) |
| `UID=edominguez.parasol` | Plex login: `username.company` format |
| `PWD=` | Empty — we're using IAM token, not a password |
| `CustomProperties=...` | Plex-specific extra config: sets auth method and passes the token |

**Why `CustomProperties` is last:** It contains semicolons inside it (`authmethod=iam; accesstoken=...`). If it's not last, the driver misreads the semicolons as separators between connection attributes. Putting it at the end means "everything from here is CustomProperties."

---

## GCP services map

```mermaid
graph TD
    subgraph "Compute"
        CRJ[Cloud Run Job\nplex-etl\nRuns our container]
    end

    subgraph "Storage"
        BQ[BigQuery\nplex_sandbox dataset\nThe data warehouse]
        AR[Artifact Registry\nStores Docker images]
    end

    subgraph "Secrets"
        SM[Secret Manager\nplex-access-token\nThe Plex IAM token]
    end

    subgraph "Scheduling"
        CS[Cloud Scheduler\nFires at 2 AM UTC]
    end

    subgraph "Identity"
        SA[Service Account\nplex-etl-sa\nThe job's identity]
        IAM[IAM Roles\nWhat the SA is allowed to do]
    end

    CS -->|triggers| CRJ
    SA -->|authorizes| CRJ
    IAM -->|granted to| SA
    CRJ -->|reads| SM
    CRJ -->|writes| BQ
    AR -->|source image for| CRJ
```

**IAM roles granted to `plex-etl-sa`:**

| Role | What it allows |
|---|---|
| `roles/bigquery.dataEditor` | Read and write tables in BigQuery |
| `roles/bigquery.jobUser` | Run BigQuery queries (counting, loading) |
| `roles/secretmanager.secretAccessor` | Read secret versions from Secret Manager |
| `roles/artifactregistry.reader` | Pull Docker images from Artifact Registry |
| `roles/run.invoker` | Be invoked by Cloud Scheduler |

---

## The incremental sync system

The pipeline tracks what it has already loaded so it doesn't pull the same data twice. This is stored in the `sync_metadata` table in BigQuery.

```mermaid
graph TD
    START([Job starts]) --> CHECK{Is this the\nfirst run?}
    CHECK -->|Yes — no row in sync_metadata| EPOCH[Use Jan 1, 1970 as the cutoff\nPulls all data ever]
    CHECK -->|No — found last sync timestamp| LASTSYNC[Read MAX timestamp\nfrom sync_metadata]
    LASTSYNC --> BACKFILL[Subtract 5 minutes\nbuffer for late arrivals]
    EPOCH --> QUERY[Query Plex with cutoff timestamp]
    BACKFILL --> QUERY
    QUERY --> WRITE[Write rows to BigQuery]
    WRITE --> UPDATE[Update sync_metadata\nwith new max timestamp]
    UPDATE --> END([Job done])
```

> **Note for Part_v_Part (current table):** Parts master data doesn't have a timestamp column, so the pipeline uses `WRITE_TRUNCATE` — it replaces the entire table on every run instead of appending. The `sync_metadata` table still records the run, but the cutoff timestamp isn't used for filtering.

---

## Common errors and what they mean

| Error | Plain English | Fix |
|---|---|---|
| `HY000 3059: data source not defined` | The ODBC driver tried to look up the DSN but the DSN config was dropped | This means the code accidentally used DSN-based auth instead of driver-direct — check `get_odbc_connection()` in `main.py` |
| `HY000 10300: service not found` | Connected to the ODBC server OK, but asked for a service name that doesn't exist on that server | `ServerDataSource=ReportDataSource` works on the test host; production uses a different name |
| `28000: Invalid authorization specification` | Username/password auth failed | Wrong `PLEX_ODBC_USER`, `PLEX_ODBC_PASSWORD`, or `PLEX_COMPANY_CODE` |
| `403: Policy update access denied` | Tried to assign IAM roles but your account isn't a project owner | Ask a GCP admin to grant you `roles/owner` on the project |
| `409: Already Exists` in Terraform | Resource exists in GCP but Terraform doesn't know about it (state mismatch) | Import the resource: `terraform import <resource> <id>` |
| `Secret not found` in Cloud Run | Secret version doesn't exist yet | Run `gcloud secrets versions add plex-access-token ...` to add the token |

---

## Glossary

| Term | Definition |
|---|---|
| **ETL** | Extract, Transform, Load — the pattern of pulling data from a source (Plex), reshaping it, and loading it to a destination (BigQuery). This pipeline is mostly Extract + Load; Transform is minimal. |
| **ODBC** | Open Database Connectivity — a standard interface for connecting to databases. Like a universal database driver. |
| **DSN** | Data Source Name — a named ODBC connection config defined in `/etc/odbc.ini`. We don't use DSN for our connection because unixODBC drops attributes when routing through it. |
| **IAM** | Identity and Access Management — controls who (people or services) can do what in GCP. Also used by Plex for token-based auth. |
| **Service Account** | A GCP identity for a machine/app (not a human). Used by Cloud Run to authenticate to other GCP services. |
| **BigQuery** | Google's managed data warehouse. SQL-queryable, handles massive datasets, optimized for analytics reads. |
| **Cloud Run** | GCP's serverless container platform. Runs Docker containers on demand, no server management. |
| **Cloud Scheduler** | GCP's managed cron service. Fires HTTP requests on a schedule. |
| **Artifact Registry** | GCP's private Docker registry. Where the pipeline's container image is stored. |
| **Secret Manager** | GCP's encrypted secrets store. Replaces `.env` files in production. |
| **Terraform** | Infrastructure-as-code tool. Defines GCP resources in `.tf` files and creates/manages them with `terraform apply`. |
| **WRITE_TRUNCATE** | BigQuery write mode that deletes and replaces the entire table. Used for full-refresh tables with no timestamp column. |
| **WRITE_APPEND** | BigQuery write mode that adds rows without deleting existing ones. Used for incremental tables. |
| **DataDirect OpenAccess SDK** | The specific ODBC driver Plex uses. A C library binary (`.so` file) that implements the ODBC protocol for Plex's server. |
