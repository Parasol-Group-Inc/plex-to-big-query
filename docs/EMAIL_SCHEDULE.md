# Email & Schedule Reference

Full inventory of every Cloud Run Job that emails a report, when it runs,
what it's actually made of, and who hears about it. Built 2026-08-13 while
standardizing report naming across the whole pipeline (see
[OPERATIONS.md](OPERATIONS.md) for the retry mechanism this depends on).

## The short version

- **16 Cloud Run Jobs** (8 report pipelines × prod/test), each running once
  a day, each sending exactly one email per run.
- **Baseline: 16 emails/day** if nothing fails. A failed run adds a second
  email that same day (its own failure notice + the 9:45 PM Mountain retry's
  outcome) — so the real ceiling is 32/day, only reached if every single
  job fails on the same day.
- **Every email goes to the same 3 people, prod and test alike** —
  `emilio.dominguez@parasolgroupinc.com`, `jennilyn.tockstein@parasolgroupinc.com`,
  `marketing@parasolgroupinc.com`. No separate test-only recipient list
  exists — see "Worth deciding" below.
- **32 Cloud Scheduler jobs** back these 16 jobs (one normal trigger + one
  retry trigger each) — confirmed via `gcloud scheduler jobs list`, no
  orphans. (Two *other* schedulers — `monday-daily-sync` and
  `monday-daily-sync-VoxScorecardsLive` — also live in this GCP project but
  belong to an unrelated Monday.com integration, not this pipeline. Left
  untouched.)

## Full schedule

**Updated 2026-08-19**: every time below is now Mountain time (`America/Denver`,
handles MST/MDT automatically), not UTC — the whole cascade was moved off
UTC specifically so nothing lands as an early-morning/odd-hour email.
Retry only fires *real* work (and a second email) if that day's scheduled
run status was `failed` — a `success` or `partial` day makes the retry a
silent no-op, no email sent. Retry itself always fires at the same instant
for every job: `9:45 PM America/Denver` (moved from 6 AM the same day —
15 minutes after the last main job in the cascade below, so every job has
had a chance to finish before the retry checks for failures).

| Category | Reports produced (email body lists each by this name) | Prod job | Prod time | Test job | Test time |
|---|---|---|---|---|---|
| **Sales** | Sales Orders, Vox \| Open Sales Orders, Pending Approval Orders, Report for Orders Past 14 Days Old, Orders Over $10k, Orders Over 10k Bottles, Customer List by Sales Rep, Revenue per Sales Rep, Orders Pending Approval by Accounting | `plex-etl` | 7:00 PM | `plex-etl-test` | 7:10 PM |
| **Production** | Work Orders, MFG Job Schedule, Labeling \| Open WO: Results, Printing Open Work Orders | `plex-etl-work-orders` | 7:20 PM | `plex-etl-work-orders-test` | 7:30 PM |
| **Supply Chain** | Vox \| Open Purchase Orders, Purchase Orders to Approve: Results | `plex-etl-purchasing-open-orders` | 7:40 PM | `plex-etl-purchasing-open-orders-test` | 7:50 PM |
| **Supply Chain** | Vox \| Products to be Discontinued | `plex-etl-part-obsolescence` | 8:00 PM | `plex-etl-part-obsolescence-test` | 8:10 PM |
| **Supply Chain** | Inventory Activity Detail Usage Per Month | `plex-etl-inventory-activity` | 8:20 PM | `plex-etl-inventory-activity-test` | 8:30 PM |
| **Inventory** | Current Inventory Snapshot, Vox \| Inventory Valuation Summary | `plex-etl-inventory-snapshot` | 8:40 PM | `plex-etl-inventory-snapshot-test` | 8:50 PM |
| **Quality** | Quality Nonconformance, Turn Around Time Report, Quality Deviations | `plex-etl-quality-nonconformance` | 9:00 PM | `plex-etl-quality-nonconformance-test` | 9:10 PM |
| **Supply Chain** | Part On-Hand Inventory, Inventory Risk Analysis | `plex-etl-part-on-hand-inventory` | 9:20 PM | `plex-etl-part-on-hand-inventory-test` | 9:30 PM |

Prod/test pairs are staggered 10 minutes apart (was 1 hour), 7:00 PM
through 9:30 PM Mountain — the whole cascade now fits inside a 7-10 PM
window instead of spanning 2 AM-5 PM UTC (which landed as roughly 8 PM the
prior day through 11 AM Mountain — i.e. squarely through the early-morning
hours this change was meant to avoid).

**Reports produced, updated 2026-08-19**: each category's report list above
now reflects every `bq_view` actually deployed as of today, not just the
original one per category — several categories quietly grew additional
reports over time (7 new ones on Sales alone) whose SQL had never actually
been pushed to GCS until today's deploy (see "What changed today" below).

## What "category" actually controls

As of the 2026-08-12/13 naming cleanup, every report config
(`reports/*.yaml`) declares a `category` and each of its `bq_view` entries
a `display_name`. `email_utils.py` uses these to build the subject —
**one subject shape per category, identical for prod and test** — e.g.:

```
[Plex ETL] Production: Work Orders, MFG Job Schedule, Labeling | Open WO: Results — 2026-08-13
[Plex ETL] Quality: Quality Nonconformance — 2026-08-13
```

**Updated 2026-08-13, same day:** status (SUCCESS/PARTIAL/FAILED) was removed
from the subject entirely, not just environment. A pipeline can produce
several peer reports in one run, and one aggregate status in the subject
was misleading when only some of them failed — e.g. a labeling view
failing while work_orders/mfg_job_schedule succeeded would show "FAILED"
and read as "nothing worked." Status now lives in the body only (next to
the Events/Errors that explain it), same reasoning that already moved
PRODUCTION/TEST out of the subject. This also means the subject is now
100% identical between a category's prod and test run on the same day —
not just "one shape," literally the same string.

PRODUCTION vs TEST no longer appears in the subject at all — it shows as a
colored badge next to the status badge in the email body (blue
"PRODUCTION" / amber "TEST"), plus a plain `Environment: PRODUCTION`/`TEST`
line in the text version. Derived from `BQ_DATASET` (`PlexProd`/`PlexTest`),
not from the job's `report_name`, so it can't drift out of sync with which
dataset a run actually wrote to.

**Before this change:** subjects varied per report_name string (e.g.
`Work Orders` vs `Work Orders Test`), and a pipeline producing more than
one named report (work_orders, sales_orders, inventory_snapshot) only ever
showed its first/generic report in the subject — e.g. "Labeling | Open WO:
Results" was invisible behind a "Work Orders" subject even on runs that
produced it. Verified fixed via a mocked SendGrid send (rebuilt image,
patched `SendGridAPIClient.send`) across prod/test and multi/single-view
cases — subjects are byte-identical between a category's prod and test run.

## Real run history (job_run_log, as of 2026-08-13)

Queried directly against `PlexProd.job_run_log`/`PlexTest.job_run_log`
(excludes local-dev noise rows like `scratch_test_*.yaml` — those come from
`docker compose run` testing on this machine, never a real Cloud Run
execution, and use a different `job_name` key so they can't corrupt real
retry-skip logic):

- `plex-etl` / `plex-etl-test`: running since 2026-07-21, 23–26
  `success` rows each — the oldest, most stable jobs.
- `plex-etl-work-orders`: 23 `success` + **1 `failed`** (2026-07-21) — the
  one real example of the retry mechanism actually mattering in this
  dataset.
- The 6 newer NetSuite-parity jobs (purchasing, obsolescence, inventory
  activity/snapshot, quality nonconformance, part-on-hand): 1–4 rows each,
  all `success` — consistent with their 2026-08-10/11/12 deploy dates, not
  a sign of anything wrong.

## What changed today (standardization)

1. Added `category` + per-view `display_name` to all 8 report configs
   (prod + test = 16 files) — `work_orders`, `sales_orders`, and
   `inventory_snapshot` already had it from the previous round; added it to
   `purchasing_open_orders`, `part_obsolescence`, `inventory_activity`,
   `quality_nonconformance`, `part_on_hand_inventory` today.
2. Rewired `email_utils.py` so environment (prod/test) is derived from
   `BQ_DATASET`, shown only in the body, and never affects the subject.
3. Audited all 16 Cloud Run Jobs + 32 Cloud Scheduler jobs against
   Terraform — **zero orphans found**, nothing to delete. The 2
   `monday-daily-sync*` schedulers in the same project are a different
   system entirely.
4. Pushed the 5 new config files to GCS via `gcloud storage cp` (a
   `terraform apply` attempt was blocked mid-session) — functionally
   correct (content confirmed live and matching), but `gcloud storage cp`
   with no `--content-type` flag reset those objects' remote content-type
   to `application/octet-stream`. Terraform's config had *already*
   correctly declared `content_type = "text/plain"` for all 16 report-config
   objects the whole time — this wasn't a missing Terraform setting, just
   `gcloud` overwriting metadata Terraform already wanted right.
   **Resolved same session**: `terraform apply -target=...` on the 10
   affected objects reconciled it (10 destroyed, 10 recreated with correct
   content-type, same content). `terraform plan` now shows 0 add/0 destroy
   — only the pre-existing image-tag cosmetic drift remains (see below).

## What changed 2026-08-19

1. **Full schedule cascade moved from UTC to Mountain time.** All 32
   Cloud Scheduler jobs (16 main + 16 retry) now fire between 7:00 PM and
   9:45 PM `America/Denver` instead of scattered across 2 AM-5 PM UTC (main
   jobs) and a fixed 6 AM Mountain (retry) — see "Full schedule" above for
   the new per-category times. `scheduler_time_zone` changed from `UTC` to
   `America/Denver` in `terraform.tfvars`; every per-category `schedule`
   literal in `main.tf` was recomputed for the new window; `retry_scheduler_cron`
   moved from `0 6 * * *` to `45 21 * * *`. Confirmed live via
   `gcloud scheduler jobs list` — all 32 `plex-*` jobs on the new times, the
   2 unrelated `monday-daily-sync*` jobs untouched.
2. **`quality_deviation_report` added** — 3rd `bq_view` on
   `plex-etl-quality-nonconformance(-test)`, correlating Quality Deviations
   to Jobs/Problems/Parts/Workcenters. See
   `catalog/plex_quality_views_catalog.md` "Deviations" section for the
   schema discovery and `reports/sql/quality_deviation_view.sql` for the SQL.
3. **12 previously-orphaned SQL files deployed for the first time.**
   Terraform only tracks a GCS bucket-object per SQL file it has an explicit
   resource for — it doesn't infer new files from a yaml's `bq_view` list.
   Several bq_views added to already-deployed categories over time (7 on
   `sales_orders`, 2 on `work_orders`, 1 each on `purchasing_open_orders`,
   `part_on_hand_inventory`, and `quality_nonconformance` itself) never got
   a matching `google_storage_bucket_object` resource, so their SQL sat in
   the repo but was never actually pushed to GCS — `quality_turnaround_time_report`
   had been silently broken this way since 2026-08-14. Fixed: uploaded all
   12 files, added the missing Terraform resources (12 to add, 0 changed),
   and verified every affected job's views build cleanly by executing each
   test job directly. Two more real bugs turned up during that verification
   (both fixed same session, not pre-existing-and-ignored):
   - `quality_deviation_view.sql` compared an `INT64`-cast key against a
     `STRING` key (both `raw_Part_v_Job` and `raw_Quality_v_Problem` are
     currently empty ahead of Monday's real data load, so BigQuery typed
     their key columns as STRING) — fixed with symmetric `SAFE_CAST` on
     both sides of every join.
   - `mfg_job_schedule_view.sql` broke from the opposite direction: real
     data just started landing in `Part_v_Lot_Shelf_Life`, revealing it's
     actually typed `DATETIME`, not the numeric duration originally
     guessed — `SAFE_CAST(... AS FLOAT64)` has no valid cast path from
     DATETIME at all, so it failed even with SAFE_CAST. Fixed by passing
     it through as a raw STRING instead (still unconfirmed what the value
     means business-wise — just no longer crashing the view).

## Worth deciding (not changed — needs a call, not a guess)

- ~~Test runs email the same 3 real people as prod~~ **Decided 2026-08-21:
  keep as-is.** Emilio confirmed no change needed — test emails continue
  going to all 3 recipients (`emilio.dominguez@`/`jennilyn.tockstein@`/
  `marketing@parasolgroupinc.com`). Revisit only if that inbox noise
  actually becomes a problem in practice.
- **Renaming `plex-etl`/`plex-etl-test`** to match the newer
  `plex-etl-{report}` pattern was considered and **rejected as not worth
  it** — Cloud Run Job names are immutable, so this would mean Terraform
  destroying and recreating the job (losing execution history) plus
  updating `cloudbuild.yaml`'s `_CR_JOB` substitution and the scheduler
  target. Real risk for a purely cosmetic gain, given naming already reads
  fine in context (it's the original/sales-orders job, predates the
  `-work-orders`/`-inventory-snapshot` naming convention).
- ~~The image-tag cosmetic drift...~~ **Resolved 2026-08-13.** Every
  `google_cloud_run_v2_job` now has `lifecycle { ignore_changes = [image,
  client, client_version] }` — Terraform no longer tracks the deployed
  image at all, so it can't drift *or* get silently reverted by an
  unrelated `terraform apply`. `image_url` in `terraform.tfvars` is now
  always a pinned commit SHA (never `:latest`) and only matters for
  first-time job creation; `deploy/cloudbuild.yaml`'s single `deploy-all`
  step (all 16 jobs, one loop) — or a manual `gcloud run jobs update
  --image=...`— is the only thing that ever moves a job onto a new image.
  Verified live: `terraform plan` shows `No changes` immediately after a
  real `gcloud run jobs update`, both right after adding the lifecycle
  block and again after a full rebuild+redeploy to commit `2f235d2`.
