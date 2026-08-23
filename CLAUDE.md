# plex-to-big-query — orientation

A Plex ERP → BigQuery ETL pipeline (Cloud Run Jobs + Cloud Scheduler +
Terraform), plus a parallel research effort mapping company reporting
(Google Sheets, NetSuite saved searches, a company-wide "Reports List")
onto what's actually buildable from Plex.

## Where live status actually lives

This repo tracks its own state obsessively — read these before assuming
anything is undocumented or before re-deriving status from scratch:

- **`CHANGELOG.md`** — top entries are the most recent, dated (not
  versioned). Every deploy/behavior change gets an entry here.
- **`reports-list/*.md`** — company-wide report inventory, one file per
  department (Production, Sales, Quality, Supply Chain, Warehouse). Each
  row has a status (✅ built, 🛠 scaffolded, 🔍 mapped, ❌ out of scope, etc.
  — legend in `reports-list/REPORTS_LIST_CATALOG.md`).
- **`spreadsheets/*.md`** — Google Sheets this project is mapping to
  Plex/BigQuery. Hub table: `spreadsheets/SPREADSHEET_CATALOG.md`.
  Multi-tab sheets get a per-tab tracker (see `mfg_job_schedule.md`).
- **`docs/*_BUILD_PLAN.md`** — detailed build logs for specific efforts
  (e.g. `NETSUITE_REPORT_BUILD_PLAN.md`, `MFG_JOB_SCHEDULE_BUILD_PLAN.md`).

**Don't trust "deployed to test" to mean prod is current too.** Historically
on this project it has meant test-only — `gcloud storage cp`/manual pushes
during iteration went to the `test/` GCS path and prod lagged behind.
Before assuming production config is current, run:

```bash
cd terraform && terraform plan -var-file=terraform.tfvars
```

If it shows `google_storage_bucket_object.*_config_prod` changing, prod is
stale — `terraform apply` syncs it (terraform manages both `reports/*.yaml`
and `test/*.yaml` GCS objects as `source`-linked resources, so apply is
the reliable deploy mechanism, not just the manual `gcloud storage cp`
shown in `docs/OPERATIONS.md` for quick iteration).

## Quick health check after any repo move / long gap

```bash
docker compose build && docker compose up   # then: docker compose down
```

Uses `.env` (OUTPUT_MODE=local) — pulls `Part_v_Part` from the real Plex
test host and writes a CSV to `./output/`, no BigQuery write, no email.
Safe, read-only, and the fastest way to confirm Docker/ODBC/credentials
all still work.

## Verifying a report deploy actually worked

**`gcloud run jobs execute ... --wait` exiting 0 does NOT mean the report's
BigQuery view got created.** The container can finish successfully (raw
table extractions all succeeded) while the view-creation step fails and
the job still reports "PARTIAL" status/exit 0 — this bit two brand-new
reports on their first real run (2026-08-23): `purchasing_pending_requisitions_report`
sent a real "PARTIAL PRODUCTION" email, `quality_supplier_returns_pending_report`
a "PARTIAL TEST" one, both from the same root cause (see below). After any
`gcloud run jobs execute`, confirm the view itself, don't trust the exit
code alone:

```bash
bq query --use_legacy_sql=false --project_id=voxdatalake \
  "SELECT COUNT(*) FROM \`voxdatalake.PlexTest.<report_name>\`"
```

**Root cause of both failures — a recurring pattern in this repo:** a raw
table with 0 rows gets BigQuery-autodetected as all-`STRING`; a sibling
table with real rows gets proper types (`INT64`, etc.). A JOIN between
them without `SAFE_CAST` on *both* sides fails view creation outright
("No matching signature for operator ="). This has now hit
`sales_order_allocation_view.sql`, `purchasing_pending_requisitions_view.sql`,
and `quality_supplier_returns_pending_view.sql` — when writing a new
report SQL, `SAFE_CAST(x AS INT64)` on both sides of every join is
cheap insurance, not just for empty tables today but for tables that are
empty in test/dev but real in prod (or vice versa).

## Known friction

- **GitHub push access**: as of 2026-08-22, `git push origin main` fails
  with `403 Permission ... denied to emiliodom` even though `gh auth
  status` shows a valid token with `repo` scope — this is an org/repo
  permission on the `emiliodom` account, not a local git/token problem.
  Don't waste time retrying; ask Emilio to sort out repo access first.
- **gcloud reauth**: `gcloud storage`/`gcloud run` calls can fail with
  "Reauthentication failed. cannot prompt during non-interactive
  execution" even though `gcloud auth list` shows an active account — an
  org security policy requiring periodic interactive re-login. Needs a
  human to run `gcloud auth login` in their own terminal; can't be
  scripted around.

## Convention

Every commit that changes behavior, infrastructure, or a deployed report
gets a matching `CHANGELOG.md` entry, added in the same commit, plus a
status-line update in whichever `reports-list/`/`spreadsheets/` doc tracks
that report. Doc-only typo fixes don't need one.

**Report docs (added 2026-08-23):** every deployed `bq_view` report also
gets a business-facing doc in `docs/reports/` (see
`docs/reports/REPORT_CATALOG.md` for the template and full list) — written
for the team/ClickUp, not engineers, since the code already has comments
and the full technical history lives in `reports-list/`/`spreadsheets/`.
Any change to a report's YAML/SQL needs a matching update to its
`docs/reports/*.md` doc, in the same commit.
