# Plex → BigQuery Pipeline — Team Guide

> **Purpose of this page:** everything a team member needs to find, access, monitor, and modify the Plex-to-BigQuery data pipeline — without reading the codebase. For deeper technical detail, see the [GitHub repo](https://github.com/Parasol-Group-Inc/plex-to-big-query).
>
> **Last updated:** 2026-07-20 · **Owner:** Emilio Dominguez

---

## 1. What this pipeline does

Every night, Cloud Run jobs pull data from **Plex ERP** (via ODBC) and load it into **Google BigQuery**, where clean report views are ready for dashboards and analysis. After every run, an email report goes to the team.

```
Plex ERP ──ODBC──▶ Cloud Run Job ──▶ BigQuery raw tables ──▶ BigQuery report VIEW
                        ▲                                          │
                 reads config from                                 ▼
                 Cloud Storage (YAML + SQL)                 Email report (SendGrid)
```

**The key design idea:** *what* the pipeline extracts and *how* the report is built live in editable files in Cloud Storage — not in code. Changing a filter, a column, or a JOIN requires **no deployment**: edit the file, and the next run picks it up.

---

## 2. Where everything lives on GCP

**Project:** `voxdatalake` · **Region:** `us-central1`
Console: https://console.cloud.google.com/home/dashboard?project=voxdatalake

| What | Where | Direct link |
|---|---|---|
| **Report data (query here)** | BigQuery → `PlexProd` dataset | [BigQuery Console](https://console.cloud.google.com/bigquery?project=voxdatalake) |
| Test data | BigQuery → `PlexTest` dataset | same link |
| **Pipeline jobs** | Cloud Run → Jobs | [Cloud Run Jobs](https://console.cloud.google.com/run/jobs?project=voxdatalake) |
| **Report definitions (YAML + SQL)** | Cloud Storage → `voxdatalake-report-configs` | [GCS bucket](https://console.cloud.google.com/storage/browser/voxdatalake-report-configs?project=voxdatalake) |
| Schedules | Cloud Scheduler | [Scheduler](https://console.cloud.google.com/cloudscheduler?project=voxdatalake) |
| Credentials (Plex token, SendGrid key) | Secret Manager | [Secrets](https://console.cloud.google.com/security/secret-manager?project=voxdatalake) |
| Container images | Artifact Registry → `plex-pipeline` | [Artifact Registry](https://console.cloud.google.com/artifacts?project=voxdatalake) |
| CI/CD builds | Cloud Build → History | [Cloud Build](https://console.cloud.google.com/cloud-build/builds?project=voxdatalake) |
| Run logs | Cloud Run → job → Executions → Logs | via Cloud Run Jobs link above |
| **Terraform state (shared)** | Cloud Storage → `voxdatalake-terraform-state` | [GCS bucket](https://console.cloud.google.com/storage/browser/voxdatalake-terraform-state?project=voxdatalake) |

### The four pipelines

Note: this table predates several newer Cloud Run jobs added since 2026-07-20 (purchasing, part obsolescence, inventory activity/snapshot, quality nonconformance, part on-hand inventory) — see docs/EMAIL_SCHEDULE.md for the complete current picture of all 16 jobs.

| Job | What | Writes to | Schedule (Mountain) |
|---|---|---|---|
| `plex-etl` | Sales Orders — **production** | `PlexProd` | 7:00 PM daily |
| `plex-etl-test` | Sales Orders — test | `PlexTest` | 7:10 PM daily |
| `plex-etl-work-orders` | Work Orders — **production** | `PlexProd` | 7:20 PM daily |
| `plex-etl-work-orders-test` | Work Orders — test | `PlexTest` | 7:30 PM daily |

### The report views (what analysts should query)

| View | Contents |
|---|---|
| `voxdatalake.PlexProd.sales_orders_report` | One row per sales order line item — order, customer, reps, part, qty, pricing, product type/group, dates |
| `voxdatalake.PlexProd.work_orders_report` | One row per job operation — job, part, workcenter, planned vs actual hours, downtime, dates |

Raw tables (prefix `raw_`) hold unprocessed Plex data — query the **views**, not the raw tables, unless debugging.

---

## 3. Who has access

| Identity | Type | Access |
|---|---|---|
| `emilio.dominguez@parasolgroupinc.com` | Human — pipeline owner | Project Owner (full admin) |
| `jennilyn.tockstein@parasolgroupinc.com` | Human — second Owner | Project Owner (full admin) — confirmed 2026-07-20; can recover access for the team if Emilio's account is ever lost |
| `plex-etl-sa@voxdatalake.iam.gserviceaccount.com` | Service account (the pipeline itself) | BigQuery Data Editor + Job User, Secret Accessor, Artifact Registry Reader, Run Invoker, Storage Object Viewer on the config bucket |

**Email report recipients:** emilio.dominguez@, jennilyn.tockstein@, marketing@ (parasolgroupinc.com)

To see the current full list of who has project access (this table can drift):
**Console:** IAM & Admin → IAM ([direct link](https://console.cloud.google.com/iam-admin/iam?project=voxdatalake)), or:

```bash
gcloud projects get-iam-policy voxdatalake --format="table(bindings.role,bindings.members)" --flatten="bindings[]"
```

### Granting someone access

| They need to… | Give them |
|---|---|
| Query the reports in BigQuery | `roles/bigquery.dataViewer` + `roles/bigquery.jobUser` |
| Edit report configs in GCS | `roles/storage.objectAdmin` on `voxdatalake-report-configs` |
| Run / debug the pipeline | `roles/run.developer` + `roles/logging.viewer` |
| Run `terraform plan`/`apply` | Project `roles/editor` (to manage resources) + `roles/storage.objectAdmin` on `voxdatalake-terraform-state` (to read/write shared state) |
| Full admin | `roles/editor` (or Owner — use sparingly) |

IAM & Admin → IAM → **Grant access** → enter their Google account email → pick role.

> **Terraform state is shared** (`gs://voxdatalake-terraform-state/`, migrated 2026-07-20) — anyone with the role above can safely run `terraform plan`/`apply` from their own clone of the repo. Just run `terraform init` after cloning; it connects to the shared backend automatically. `terraform.tfvars` itself is gitignored (contains real values) — get a copy from whoever last applied, or reconstruct it from `terraform.tfvars.example` plus the live values in this guide.

---

## 4. How to run a job manually

Runs are scheduled nightly, but you can trigger one any time (safe to re-run — each run fully replaces the data it loads):

**Console:** Cloud Run → Jobs → pick the job → **Execute**.

**CLI:**
```bash
gcloud run jobs execute plex-etl-test --region=us-central1 --project=voxdatalake --wait
```

> ⚠ **Rule of thumb: always run the `-test` job first.** Test jobs write to `PlexTest` — safe to run repeatedly. Only trigger the prod job after the test email comes back SUCCESS.

### Reading the email report

Every run emails a summary. Subject format: `[Plex ETL] Sales: Sales Orders, Vox | Open Sales Orders — 2026-08-13` (one subject per category, identical for prod/test — status is NOT in the subject, see below).

| Badge | Meaning | What to do |
|---|---|---|
| 🟢 SUCCESS | Everything ran clean | Nothing |
| 🟡 PARTIAL | Some extractions or the view update failed; the rest completed | Read the **Errors** section of the email — it names the exact failure |
| 🔴 FAILED | The job crashed before completing | Check Cloud Run logs (link is in the email footer) |

---

## 5. How to modify an existing report

Report definitions live in `gs://voxdatalake-report-configs/`:

```
voxdatalake-report-configs/
├── reports/               ← production configs
│   ├── sales_orders.yaml       (which Plex views to pull, filters)
│   └── work_orders.yaml
├── test/                  ← test configs (same, but → PlexTest)
│   ├── sales_orders.yaml
│   └── work_orders.yaml
└── sql/                   ← the report JOIN logic
    ├── sales_orders_view.sql
    └── work_orders_view.sql
```

**No deployment needed for any of these changes** — the next run picks them up.

### Change a filter or add/remove a Plex view (YAML)

1. Edit the file — either directly in the [GCS Console](https://console.cloud.google.com/storage/browser/voxdatalake-report-configs?project=voxdatalake) (click file → Edit) or locally in the repo (`reports/`) and push:
   ```bash
   gcloud storage cp reports/test/sales_orders.yaml gs://voxdatalake-report-configs/test/
   ```
2. Run the **test** job and check the email + data in `PlexTest`.
3. Apply the same edit to the prod YAML (`reports/` path in the bucket).

YAML rules (enforced — a bad entry is skipped and flagged in the email):
- `plex_view`, `bq_table`, `date_col`: letters, digits, underscores only
- `filter`: a SQL WHERE clause; must not contain `;`, `--`, or `/*`

### Change report columns or JOIN logic (SQL)

1. Edit the `.sql` file (locally in `reports/sql/` is best — it's version-controlled):
   ```bash
   gcloud storage cp reports/sql/sales_orders_view.sql gs://voxdatalake-report-configs/sql/
   ```
2. Run the test job — the view is recreated during the run.
3. Query the view in `PlexTest` to verify, then run the prod job.

Two SQL rules that will save you pain (learned the hard way — full story in the repo's `docs/CODE_REVIEW_2026-07-14.md`):
- Always use the `{gcp_project}` and `{dataset}` placeholders — never hardcode `voxdatalake.PlexProd`.
- Date columns arrive from Plex as huge integer nanoseconds. Use the conversion pattern documented in the repo's `CHEATSHEET.md` ("dates as huge numbers") — don't invent your own cast.

---

## 6. How to add a brand-new report

High level: **two files in GCS + one Terraform block**. Full walkthrough with copy-paste templates: repo → `docs/OPERATIONS.md` → "Add a Brand-New Report".

1. **Find your Plex views** — browse the repo's `catalog/plex_catalog_index.md` (all ~2,000 Plex ODBC views indexed by database: Sales, Part, Accounting, …).
2. **Create the YAML** (copy `reports/work_orders.yaml` as a template): list each Plex view → BigQuery raw table, plus the report view name and SQL file path. Make a test copy in `reports/test/` pointing at `PlexTest`.
3. **Write the SQL** (copy `reports/sql/work_orders_view.sql`): the JOIN that turns raw tables into the report view.
   - ⚠ If your report needs a table another report already extracts (e.g. `raw_Part_v_Part`), **reference it in SQL but do NOT re-extract it** — two pipelines writing the same table can wipe it.
4. **Upload both to GCS** (`reports/`, `test/`, and `sql/` paths as above).
5. **Add two Cloud Run jobs in Terraform** (test + prod) — copy the `etl_work_orders` blocks in `terraform/main.tf`, change the job name, config path, and schedule. Then:
   ```bash
   cd terraform && terraform apply -var-file=terraform.tfvars
   ```
6. **Run the test job, verify, then enable prod.** Add `category: YourCategory` and a `display_name` on each `bq_view` entry in the YAML so the email subject reads `[Plex ETL] YourCategory: Your Report Name — DATE` — the same shape every day, identical between prod and test (status is never in the subject, only in the body).

---

## 7. Changing code (Python / Docker) — when it's actually needed

Only needed for changes to pipeline *behavior* (email format, error handling, new config capabilities) — never for report content. Deploys go through Cloud Build:

```bash
gcloud builds submit --config deploy/cloudbuild.yaml --project=voxdatalake \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)
```

This builds the image, updates **both** sales jobs, and smoke-tests the **test job only** — production is never run automatically. After a green build, trigger prod manually.

---

## 8. Troubleshooting quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| PARTIAL email, "query failed" for one view | Plex view renamed/unavailable, or filter typo | Check the view name in `catalog/`, fix YAML, re-run |
| PARTIAL email, "view update failed" | SQL error in the `.sql` file (BigQuery only validates at CREATE) | Read the error in the email — it has the exact line/column; fix SQL, push to GCS, re-run |
| 0 rows fetched for a view | Empty view in Plex, or filter too tight | Not destructive — existing BigQuery data is preserved automatically. Verify in Plex. |
| Dates show as huge numbers | View wasn't recreated after a SQL fix | Push SQL to GCS **and re-run the job** — the view only updates during a run |
| FAILED email, ODBC connection error | Plex host down or token issue | See repo `docs/TROUBLESHOOTING.md` (error codes 10300, 3059 documented) |
| Gmail "couldn't verify this message" warning on report emails | SendGrid domain authentication not set up | SendGrid → Settings → Sender Authentication → add CNAME records to parasolgroupinc.com DNS |

Full command-level fixes: repo → `docs/TROUBLESHOOTING.md` and `CHEATSHEET.md`.

---

## 9. Known open items

| Item | Status |
|---|---|
| DataDirect ODBC driver license | ⚠ On 15-day trial — must be licensed before relying on prod long-term |
| SendGrid domain authentication | ⚠ Pending — report emails show a Gmail warning banner until DNS records are added |
| Prod work orders data | Plex prod host returns no `Job`/`Job_Op` rows yet — pipeline is ready, waiting on Plex data |

---

## 10. Repo and further reading

**GitHub:** https://github.com/Parasol-Group-Inc/plex-to-big-query

| Doc | What's in it |
|---|---|
| `CHEATSHEET.md` | Everything on one page — commands, env vars, troubleshooting |
| `docs/OPERATIONS.md` | Full guide: edit reports, add reports, SendGrid setup, safety guards |
| `docs/QUICKSTART.md` | Zero-to-running setup guide |
| `docs/FRONTEND_GUIDE.md` | The architecture explained for frontend developers |
| `catalog/plex_catalog_index.md` | Index of every Plex ODBC view, by database |
| `docs/CODE_REVIEW_2026-07-14.md` | Security/reliability review — what's guarded and why |
