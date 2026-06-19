# Plex to BigQuery ETL Pipeline

Pulls operational data from **Plex ERP** via ODBC and loads it into **Google BigQuery** on a scheduled basis. Runs as a Cloud Run Job triggered daily by Cloud Scheduler. Credentials are stored in Secret Manager and never touch the filesystem.

**GCP project:** `parasoldatalake` | **BigQuery dataset:** `plex_sandbox` | **Plex view:** `Part_v_Part` (Raw Materials)

---

## How it works

The pipeline supports two modes controlled by the `OUTPUT_MODE` environment variable. The same Docker image is used for both.

**Local mode** — verify your data extraction works before touching GCP:

```
.env (credentials)
      │
      ▼
Docker container
      │
      ├─ Connects to Plex via ODBC (real connection, real data)
      │
      └─ Writes CSV files to ./output/
```

**BigQuery mode** — production pipeline running in GCP:

```
Cloud Scheduler (cron 2 AM UTC)
      │
      ▼
Cloud Run Job
      │
      ├─ Reads IAM token from Secret Manager
      ├─ Connects to Plex via ODBC (driver-direct, IAM token auth)
      ├─ Queries Part_v_Part WHERE Part_Type = 'Raw Materials'
      ├─ Writes rows to BigQuery (WRITE_TRUNCATE — full refresh)
      └─ Sends email report via SendGrid (optional)
```

---

## Quick navigation

| What you want to do | Where to look |
|---|---|
| New here? Start here | [docs/QUICKSTART.md](docs/QUICKSTART.md) |
| Frontend dev learning the stack | [docs/FRONTEND_GUIDE.md](docs/FRONTEND_GUIDE.md) |
| Run locally and get CSV output | [LOCAL_SETUP.md](LOCAL_SETUP.md) |
| Deploy to GCP with Terraform | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) |
| Understand the data flow and config | [TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md) |
| gcloud / docker / terraform commands | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| Tear down all GCP infrastructure | [docs/TEARDOWN.md](docs/TEARDOWN.md) |
| Add tables, configure SendGrid | [docs/OPERATIONS.md](docs/OPERATIONS.md) |
| Request ODBC access from Plex support | [PLEX_SUPPORT_TEMPLATE.md](PLEX_SUPPORT_TEMPLATE.md) |

---

## Repository layout

| Path | Purpose |
|---|---|
| `main.py` | ETL entry point — ODBC query, CSV or BigQuery write, metadata tracking |
| `email_utils.py` | SendGrid email report builder |
| `requirements.txt` | Python dependencies (pinned) |
| `Dockerfile` | Container image — installs Plex ODBC driver and Python app |
| `docker-compose.yml` | Local Phase 1 runner — builds image, writes CSVs to `./output/` |
| `.env.example` | Template for your `.env` file — copy and fill in |
| `config/odbcinst.ini` | Registers the Plex ODBC driver with unixODBC |
| `config/odbc.ini` | Defines PlexProduction and PlexTest DSNs (host, port) |
| `templates/report.html` | HTML template for email run summaries |
| `driver/` | Plex Linux ODBC driver files — gitignored, must be populated manually |
| `terraform/main.tf` | All GCP infrastructure as code |
| `terraform/variables.tf` | Terraform input variable definitions |
| `terraform/outputs.tf` | Terraform outputs — copy-paste commands after apply |
| `terraform/terraform.tfvars.example` | Template for your `terraform.tfvars` file |
| `deploy/cloudbuild.yaml` | Cloud Build CI/CD pipeline definition |
| `docs/QUICKSTART.md` | Step-by-step setup guide, no prior knowledge assumed |
| `docs/FRONTEND_GUIDE.md` | Architecture study guide with diagrams, written for frontend devs |
| `docs/API_REFERENCE.md` | All gcloud, docker, terraform, and bq commands for this project |
| `docs/OPERATIONS.md` | How to configure SendGrid and add more Plex tables/reports |
| `output/` | CSV files written by local runs — gitignored |

---

## Two-phase setup

**Phase 1** — get local extraction working:
```bash
cp .env.example .env        # fill in Plex credentials
docker compose build
docker compose up
# inspect ./output/*.csv
```

**Phase 2** — deploy to GCP once extraction is verified:
```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in GCP project details
terraform init && terraform apply -var-file=terraform.tfvars
# push image, add secret versions, run job
```

Full step-by-step in [docs/QUICKSTART.md](docs/QUICKSTART.md) or the individual guides above.

---

## Current status

| Component | State |
|---|---|
| Local Docker extraction | Working — `vox.odbc.plex.com`, `ReportDataSource` |
| GCP infrastructure | Deployed — `parasoldatalake` |
| Cloud Run image | Pushed — `plex-pipeline/etl:latest` |
| Plex → BigQuery on test host | Pending first successful run |
| Plex production host (`odbc.plex.com`) | Blocked — need production `ServerDataSource` name from Plex support |
