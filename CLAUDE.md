# plex-to-big-query — orientation

A Plex ERP → BigQuery ETL pipeline (Cloud Run Jobs + Cloud Scheduler +
Terraform), plus a parallel research effort mapping company reporting
(Google Sheets, NetSuite saved searches, a company-wide "Reports List")
onto what's actually buildable from Plex.

## Where live status actually lives

This repo tracks its own state obsessively — read these before assuming
anything is undocumented or before re-deriving status from scratch:

- **`docs/OPEN_ITEMS.md`** — every open item across all projects, with owner
  and next step. **Read it first when resuming.** Delete items as they close.
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

**Don't trust "deployed to test" to mean prod is current too.** Historically,
`gcloud storage cp` pushes during iteration updated one GCS path and not the
other, and prod drifted from `main`. The truth is the plan. From the primary
folder, on a clean, pushed `main`:

```bash
cd terraform && terraform plan -var-file=terraform.tfvars
```

Anything it lists is GCS drifting from `main`. **Sync it with
`./scripts/deploy.sh`,** never a bare `terraform apply`. From a project folder,
the deploy guard refuses the plan unless you add
`TF_GUARD_OVERRIDE="read-only drift check"`, and that folder has no
`terraform.tfvars` anyway. **Never `gcloud storage cp` into the prod `reports/`
or `sql/` paths:** that is how prod diverged and a fix got rolled back
(Known friction, below).

## Folders, branches and the deploy locks (read before any git or terraform)

- **Each project has its own git worktree, bound to its branch:**

  | Folder | Branch | Use |
  |---|---|---|
  | `C:\F\Parasol\plex-to-big-query` | `main` | merge and deploy only |
  | `ptbq-scorecard` | `dev-scorecard` | Vox Scorecard |
  | `ptbq-sandbox` | `dev-sandbox` | Scorecard Sandbox |
  | `ptbq-label-design` | `dev-label-design` | Label Design |
  | `ptbq-part-lot` | `dev-part-lot` | Part Lot Attributes + inheritance |
  | `ptbq-dev` | `dev` | shared tooling |

  Work in the folder of the project you were asked about. Never
  `git switch` a project folder onto another branch; the pre-commit hook
  blocks commits if you do.
- **The hooks** (`.githooks/`, installed by `scripts/install_hooks.sh`) block:
  - non-merge commits on `main`;
  - cross-project files;
  - deployable changes without a CHANGELOG entry;
  - prod/test YAML count mismatches;
  - pushing a dev branch into `main`.

  Every block names an override env var. Use it only when the user
  explicitly wants that exception, and say so. Never `--no-verify`.
- **Deploy = `./scripts/deploy.sh` from the primary folder.**
  `terraform/main.tf` runs `scripts/tf_guard.py` as a data source on every
  plan and apply. It fails unless the folder is the primary one, on a clean
  `main` equal to `origin/main`. `TF_GUARD_OVERRIDE="why"` is for read-only
  plans, e.g. checking drift from a dev folder.
- **Check for parallel sessions.** Before editing, check that no other
  session works in the same folder/branch: a Claude Code hook reports it on
  every prompt, and `ListAgents` shows peers. Stage by explicit path, never
  `git add -A`.

## Claude Code reads as a read-only account, writes only by impersonation

Claude's gcloud/bq calls use `claude-readonly@voxdatalake.iam.gserviceaccount.com`
(config `claude`), not your login. It can read BigQuery, Cloud Run and logs
and nothing else. **Writes go through `claude-operator`,** named in that one
command (`--impersonate-service-account=claude-operator@voxdatalake.iam.gserviceaccount.com`).
That covers running jobs, BigQuery and GCS writes, and secrets. A plain
command's PERMISSION_DENIED is expected; add the flag only for an intended
write. **Deploys:** `./scripts/deploy_as_claude.sh </dev/null` for the review,
then pipe the change count in only after the user approves it. If
`echo $CLOUDSDK_ACTIVE_CONFIG_NAME` is empty, Claude is running as the user's
own login: stop and fix the setup. Details and the per-laptop setup:
`docs/CLAUDE_CODE_IAM.md`.

## Quick health check after any repo move / long gap

```bash
docker compose build && docker compose up   # then: docker compose down
```

Uses `.env` (OUTPUT_MODE=local) — pulls `Part_v_Part` from the real Plex
test host and writes a CSV to `./output/`, no BigQuery write, no email.
Safe, read-only, and the fastest way to confirm Docker/ODBC/credentials
all still work.

## Each pipeline has TWO config files, and test is not generated from prod

`reports/<pipeline>.yaml` and `reports/test/<pipeline>.yaml` are **separate,
hand-maintained files** — Terraform's `*_config_prod` points at the first and
`*_config_test` at the second (`source = ".../reports/test/sales_orders.yaml"`).
The test copy is the same extraction/view list with `report_name` suffixed
`_test` and the comments stripped; nothing generates it.

**So any change to an `extractions:` or `bq_view:` list must be made in both
files.** Editing only the prod one and then running the *test* job looks like a
successful deploy and is not: on 2026-09-09 a run picked up the old test config,
logged `Report 'sales_orders_test' loaded: 22 extraction(s)` instead of 24,
created none of the new raw tables, and **still exited 0**. The tell is that
count line in the logs — check it against `grep -c 'plex_view:'` on the config
you think you deployed:

```bash
grep -c 'plex_view:' reports/sales_orders.yaml reports/test/sales_orders.yaml
```

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

## A hand edit to a live view lasts only until the next run

Every pipeline run that extracts recreates its views from the SQL in GCS,
which `./scripts/deploy.sh` syncs from `main`. A view changed by hand in the
BigQuery console is therefore reverted by the next such run, not just by the
next deploy. Jennilyn edits views directly: `approaching_msl_report_v2` (10-27),
`bottling_job_open_with_orders_report` (10-26), and `pipeline_plex_value_report`
(10-30, Deposit Review statuses). To keep such an edit: diff the live
definition (`INFORMATION_SCHEMA.VIEWS.view_definition`) against
`reports/sql/`, put the change in the repo, check the repo SQL returns exactly
what the live view returns, then merge and deploy before the next prod slot
(1 PM / 6 PM / 11 PM MT probe, 4 AM full). Recipe: `docs/OPERATIONS.md`,
"A view was edited by hand in BigQuery".

## Bottling 9-parts count from 2026-11-01

Until 10-30, Bottling records on 9-parts were dropped as double credit for
their 5-part job (bulk cases exempt). Jennilyn removed the 5-part BOMs and
asked to count them "starting now"; the drop now applies only before
2026-11-01, in `packaging_daily_report`, `production_monthly_by_workcenter_group_report`
and `weekly_production_update_report` (and so `production_vs_goal_report`).
`*_9part_with_5_bom_qty` columns show possible double credit and should be 0
once her BOMs are finished (OPEN_ITEMS D27). Don't move the date without her.

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

## Goals — two tables, one resolver, three views

Goals are typed by people, never pulled from Plex:
- **`scorecard_goals_app`** is written by the manual-data web app
  (`deploy/manual_data_app/`, via its Google Sheet). This is where goals are
  entered now.
- **`scorecard_goals`** is the legacy table. The Apps Script that used to
  fill it (`deploy/goals_sheet_to_bigquery.gs`) was deleted on 2026-09-22.
  Its 68 rows were imported into the app in PlexTest on 2026-09-24. **The old
  deployed Apps Script project still has to be disabled by hand,** or its
  trigger keeps truncating the table.
- **`scorecard_goals_resolved`** is a view: the app's newest row per
  (metric, month, scope), falling back to the legacy table.
  `revenue_vs_goal_report`, `sales_vs_goal_report` and
  `production_vs_goal_report` all read it.

Neither table is Terraform-managed or created by the ETL, and **the resolver
fails to create if either is missing.** That looks exactly like a broken view
rather than a missing dependency. DDL and columns:
`docs/reports/scorecard_goals.md`, `docs/reports/scorecard_goals_resolved.md`.

The join that bites: `scope` is an **exact string match**, and Plex disagrees
with the scorecard's own labels. The work centre group is `Encapsulating`,
but the tile says "Encapsulation". A mismatch yields a NULL goal, not an
error, so it reads as 0% forever. The views expose `goal_without_sales` /
`goal_without_production` flags so an unmatched row surfaces. In
`sales_vs_goal_report` the company-wide goal is **its own row with actual 0**,
so don't sum `goal_value` across rows.

## Component demand is NETTED down the BOM (since 2026-10-30)

`inventory_available_to_sell_report` computes component demand by MRP netting:
each part passes down only its shortfall (demand − its own available stock),
one BOM level at a time, in low-level-code order over the single-level
`Part_v_BOM`. Approaching MSL and Out of Stock read it. Full write-up, worked
example and check queries: `docs/BOM_DEMAND_NETTING.md`.
- **Both numbers are published on purpose.** `component_demand_qty` /
  MSL `demand_qty` are netted; `gross_component_demand_qty` / MSL
  `gross_demand_qty` are the old flat explosion. Jennilyn asked to keep both.
  Don't "simplify" one away.
- **The flat BOM (`Part_v_Flat_BOM`) now only feeds the gross column.**
  Multiplying orders down it ignores intermediate stock: that was the MSL
  double count (capsule 33312-00NUT46-0 read 12.05M instead of 2,182,496).
- **Netting is unrolled to 6 levels** (`net_0` … `net_6`), the deepest BOM in
  PlexProd. If `bom_depth_beyond_netting` is ever TRUE, add a `net_7` stage.
- **BigQuery does not store CTE results.** A CTE referenced twice runs
  twice; stacked stages that each read the previous one twice went
  exponential (past two minutes). Each stage must read the previous one
  once. Keep that in mind for any staged/iterative SQL here.
- **`PlexProd.msl_demand_daily`** is the daily history of both numbers (scheduled
  query `msl_demand_daily` in Terraform, SQL `terraform/msl_demand_daily.sql`). It
  is BigQuery-only data, in the backup list; the ETL never writes it.
- The `reports/plex_sql/` copies of available-to-sell and out-of-stock carry
  the netting in T-SQL since 2026-10-30, untested in Plex (OPEN_ITEMS D13).

## Scorecard sandbox (`voxdatalake.ScorecardSandbox`)

A full simulated year under every scorecard tile, for designing Looker Studio
against: `python scripts/scorecard_sandbox/build.py` (about 7.5 min). The ETL
never writes it. Design and rules are in `scripts/scorecard_sandbox/README.md`;
what it found is in `docs/SCORECARD_SANDBOX_FINDINGS.md`. Three things to know
before touching it:

- **No random rows.** Every synthetic Plex row clones a real PlexTest row into
  the same `raw_*` table, and manual tiles read the app's tables. A shortcut
  that writes into a view's output, or invents a row from nothing, breaks the
  point of the thing.
- **It is built from a time-travel snapshot** (`build.SNAPSHOT`), because live
  PlexTest's tables stopped joining each other on 2026-09-24. BigQuery time
  travel reaches back only 7 days, so after 2026-09-30 the copy step fails
  until a new instant is picked with `snapshot_check.py`.
- **`proposed_sql/` overrides are NOT deployed.** The sandbox uses them for
  fixes found there (rep resolution, Deposit Review, scrap flag). Production
  still runs `reports/sql/`. When a fix lands there, delete its override.

## Prod ETL times live in a table, not Cloud Scheduler (since 2026-10-19)

Since probe phase 2 stage B (`docs/PROBE_BUILD_PLAN.md`), `PlexOps.etl_schedule` holds every
prod job's run times: 1 PM / 6 PM / 11 PM `probe`, plus a 4 AM `full` run. The
`etl-dispatcher` Cloud Function (called every 5 min by `plex-etl-dispatcher`)
starts what is due, and logs each start in `PlexOps.etl_dispatch_log`.
- **Change a time with SQL, not Terraform.**
- **No retries:** a failed run gets ONE follow-up probe 15 min later.
- **A Plex outage trips a breaker (since 2026-10-22).** After two runs fail
  to connect, due slots are logged `held-outage` instead of started, one
  canary probe tries every 10 min (its first failure is the only email), and
  once one connects each held job gets ONE `recovery` run. All derived from
  `etl_dispatch_log`; no state elsewhere. It matches the error prefix
  `ODBC connection failed`, so don't reword it in `main.py`.
- **Test jobs still use their own nightly schedulers.**

To ask "did prod run?", read `etl_dispatch_log`, not the Cloud Scheduler list.
The function is deployed with `gcloud functions deploy` (command in
`terraform/main.tf`), not Cloud Build.

## Job naming

`plex-etl-<pipeline>` for Cloud Run jobs, `plex-<pipeline>-sync` for schedulers
(plus a `-retry` variant each). Sales Orders was renamed off the legacy generic
`plex-etl` / `plex-etl-test` / `plex-daily-sync` on 2026-09-04 — it was the only
pipeline when the repo was built and kept the generic name afterwards, so
`gcloud run jobs execute plex-etl-sales-orders-test` (the obvious guess) failed
with NOT_FOUND.

**Cloud Run job and scheduler names are immutable — Terraform destroys and
recreates to rename.** That's safe (neither holds state), but a recreated job
is a brand-new job. It used to come up on `image_url` in `terraform.tfvars`,
which nothing kept current (several deploys stale on 2026-09-04 and again on
2026-10-22). **Since 2026-10-22 a new job starts on `local.etl_image`**, the
image `plex-etl-sales-orders` runs live (`var.image_reference_job`). The plan
prints it as the `etl_image` output: check it before a rename. Every job run
also logs its build SHA in `job_run_log.build`, and the batch digest flags a
job on a different build.

## Email subjects

`[Plex ETL] - {Category}: {Pipeline} — {date}`, built in `email_utils.py` from
each config's `category` plus its pipeline name. Changed 2026-09-04 — the
subject used to enumerate every `display_name` a run produced and hit **810
characters** once `sales_orders` reached 22 views. The full report list lives in
the body under "REPORTS PRODUCED".

Prod and test deliberately share a subject (the `_test` suffix is stripped) so
the two environments thread together; PRODUCTION/TEST shows as a body badge.
**This is a code change, so it ships via Cloud Build, not `terraform apply`.**

**Batches mail only at their ends (since 2026-10-21).** In each prod dispatcher
batch (same mode and hour in `etl_schedule`) and in the nightly test cascade,
only the first job emails its report and the last sends one digest,
`[Plex ETL] - Digest — {date}`; a failed or partial job always emails. The
roles are `EMAIL_ROLE`: set by the dispatcher for prod, fixed per test job in
Terraform. Details: `docs/OPERATIONS.md` § "Batch emails".

## Known friction

- **GitHub push access**: resolved once (2026-08-24, repo access fixed on
  the GitHub side, 22 queued commits pushed cleanly) — **recurred
  2026-09-17**, same exact signature: `git push origin main` fails `403
  Permission ... denied to emiliodom` while `gh auth status` shows a valid
  token with `repo` scope. Confirms this is an org/repo permission setting
  on GitHub's side that can silently revert, not something local
  git/token config ever actually fixes for good. Needs a human with GitHub
  org admin access to check repo access for `emiliodom` again — don't
  spend time debugging git/gh config locally when this shows up.
- **gcloud reauth**: `gcloud storage`/`gcloud run` calls can fail with
  "Reauthentication failed. cannot prompt during non-interactive
  execution" even though `gcloud auth list` shows an active account — an
  org security policy requiring periodic interactive re-login. Needs a
  human to run `gcloud auth login` in their own terminal; can't be
  scripted around.
- **A `terraform apply` from a `dev*` branch rolls back the other
  workstream — it happened** (the deploy guard above now refuses it). `80c6431` shipped the Label Design pivot fix
  to prod on 2026-09-22 from `dev-label-design`; that evening an apply from
  `dev-scorecard`, which never had the commit, rewrote
  `sql/label_design_view.sql` in GCS (2026-09-23 00:18 UTC) with the old
  view, and nothing noticed for two days. **Deploy only with
  `./scripts/deploy.sh`.** The guard refuses any other folder or branch, and
  `plan_review.py` prints what each change is and which project owns it. A
  file you didn't touch in that list means stop.
- **Line endings used to fake plan changes.** `core.autocrlf=true` rewrote
  files as CRLF on checkout and GCS held a mix, so on 2026-09-24, 8 of 30
  planned changes were identical content. `.gitattributes` now pins LF on
  everything Terraform uploads, and `plan_review.py` still separates
  "line-ending only" from real content changes in case an old CRLF object
  remains in GCS.

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
