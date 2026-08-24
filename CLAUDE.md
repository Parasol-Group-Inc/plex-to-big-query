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

**Root cause — fixed at the source 2026-08-23, not just patched per-file.**
A raw table with 0 rows used to get BigQuery-autodetected as all-`STRING`
(hardcoded in `write_to_bigquery`); a sibling table with real rows gets
proper types (`INT64`, etc.). A JOIN between them without `SAFE_CAST` on
*both* sides failed view creation outright ("No matching signature for
operator ="). This hit `sales_order_allocation_view.sql`,
`purchasing_pending_requisitions_view.sql`,
`quality_supplier_returns_pending_view.sql`, `sales_quotes_open_view.sql`,
and `sales_returns_open_view.sql` before it was fixed properly: `query_plex()`
now reads each column's real ODBC type from `cursor.description` (the same
approach `extract_schema_catalog.py` already used successfully) and
`write_to_bigquery()` uses it to type an empty table correctly from the
start, instead of forcing STRING. Populated tables are untouched —
`autodetect=True` still infers types from real row values exactly as
before, so this doesn't change behavior for anything that already works.
**Still keep `SAFE_CAST(x AS INT64)` on both sides of every join in new
report SQL anyway** — cheap insurance for the case where BigQuery's own
type inference on a *populated* column doesn't match your assumption (e.g.
a nullable int column landing as `FLOAT64` via pandas, which already
happened once for `Product_Type_Key` in this repo).

## bq_view creation order and the retry-once safety net

A `bq_view` entry can be a thin alias over a sibling view in the same
config (`SELECT * FROM other_view`, e.g.
`sales_orders_pending_approval_by_rep_view.sql`). That only works if the
sibling is created first — `main()`'s view loop (`main.py`) now retries
any view that fails on its first pass exactly once, after every other
view in that run has had a chance to be created, so a YAML-list reorder
that breaks this ordering self-heals within the same run instead of
silently leaving a stale/missing view. Don't rely on this as a substitute
for reasonable ordering, though — it only helps within one run.

## Manual Cloud Build deploys (`deploy/cloudbuild.yaml`)

`gcloud builds submit --config deploy/cloudbuild.yaml --project=voxdatalake .`
needs `SHORT_SHA` supplied explicitly — it's only auto-populated when
Cloud Build is triggered from a connected git source, not a plain local
submit:

```bash
gcloud builds submit --config deploy/cloudbuild.yaml --project=voxdatalake \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .
```

**Two real bugs in this file, found and fixed 2026-08-23 the first time it
was actually exercised end-to-end:** every custom substitution declared in
the `substitutions:` block must be referenced somewhere in the template or
the whole build is rejected at submit time (a vestigial unused `_CR_JOB`
broke this); and Cloud Build's substitution parser scans for *any*
`$WORD`/`${WORD}` pattern in every string field, including inside embedded
bash scripts — a script's own bash variables (`$job`, `$IMAGE` in the
`deploy-all` step) must be escaped as `$$job`/`$$IMAGE` or Cloud Build
tries to resolve them as (nonexistent) substitutions and fails. Also keep
`_ALL_JOBS` in sync with every `google_cloud_run_v2_job` resource name in
`terraform/main.tf` — a job missing from that list silently never gets a
new image from this pipeline again.

## Known friction

- **GitHub push access**: resolved 2026-08-24 — repo access was fixed on
  the GitHub side and 22 queued commits pushed cleanly. (As of 2026-08-22,
  `git push origin main` had been failing with `403 Permission ... denied
  to emiliodom` even though `gh auth status` showed a valid token with
  `repo` scope — an org/repo permission issue, not local git/token.)
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
