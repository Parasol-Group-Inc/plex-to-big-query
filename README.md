# Plex to BigQuery ETL Pipeline

Pulls operational data from **Plex ERP** via ODBC and loads it into **Google BigQuery** on a scheduled basis. The pipeline runs as a Cloud Run Job triggered daily by Cloud Scheduler. Credentials are stored in Secret Manager and never touch the filesystem.

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
Cloud Scheduler (cron)
      │
      ▼
Cloud Run Job
      │
      ├─ Reads credentials from Secret Manager
      ├─ Connects to Plex via ODBC
      ├─ Reads last sync timestamp from BigQuery (sync_metadata table)
      ├─ Queries only rows modified since last run
      ├─ Appends rows to BigQuery target table
      └─ Sends email report via SendGrid (optional)
```

---

## Quick navigation

| What you want to do | Where to look |
|---|---|
| Run locally and get CSV output | [LOCAL_SETUP.md](LOCAL_SETUP.md) |
| Deploy to GCP with Terraform | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) |
| Understand the data flow and config | [TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md) |
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
| `deploy/setup.sh` | Manual GCP setup script — deprecated, use Terraform |
| `deploy/cloudbuild.yaml` | Cloud Build CI/CD pipeline definition |
| `output/` | CSV files written by local runs — gitignored |

---

## Important: the SQL query is a placeholder

The `query_plex()` function in [main.py](main.py) contains a placeholder SQL query referencing a sample Plex view (`Production_Order_v_Production_Order`). You must replace this with the actual view or report name and columns confirmed with your Plex support contact before any data will flow.

See [LOCAL_SETUP.md](LOCAL_SETUP.md) Step 4 for instructions.

---

## Two-phase setup

**Phase 1** — get local extraction working:
```powershell
cp .env.example .env        # fill in Plex credentials
docker compose build
docker compose up
# inspect ./output/*.csv
```

**Phase 2** — deploy to GCP once extraction is verified:
```powershell
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in GCP project details
terraform init && terraform apply -var-file=terraform.tfvars
# push image, add secret versions, run job
```

Full step-by-step instructions in [LOCAL_SETUP.md](LOCAL_SETUP.md) and [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).
