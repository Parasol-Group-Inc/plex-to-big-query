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
