# Email & Schedule Reference

Last reviewed: 2026-09-25

Full inventory of every Cloud Run Job that emails a report, when it runs,
what it's actually made of, and who hears about it. Built 2026-08-13 while
standardizing report naming across the whole pipeline (see
[OPERATIONS.md](OPERATIONS.md) for the retry mechanism this depends on).
The schedule table below is derived from the `google_cloud_scheduler_job`
resources in `terraform/main.tf` (Sales Orders' two times come from
`scheduler_cron`/`scheduler_cron_test` in `terraform.tfvars`) — if they
disagree, `main.tf` wins; fix this page.

## The short version

- **13 pipelines, 26 Cloud Run Jobs** (prod + test), 68 BigQuery views.
  Twelve pipelines run once a day in an evening cascade; **Label Design runs
  twice a day** (9:30 AM and 1:30 PM prod, 9:40 AM and 1:40 PM test).
- **Every run sends one email** — so a normal day is **28 scheduled
  emails** (24 from the evening cascade + 4 from Label Design), plus whatever
  the 9:45 PM retries send (see the caution under the table).
- **Every email goes to the same 3 people, prod and test alike** —
  `emilio.dominguez@parasolgroupinc.com`, `jennilyn.tockstein@parasolgroupinc.com`,
  `marketing@parasolgroupinc.com` (`report_to_emails` in `terraform.tfvars`).
  No separate test-only recipient list exists — see "Worth deciding" below.
- **52 Cloud Scheduler jobs** back these 26 jobs (one normal trigger + one
  retry trigger each), named `plex-<pipeline>-sync[-test]` and
  `plex-<pipeline>-sync[-test]-retry`. (Two *other* schedulers —
  `monday-daily-sync` and `monday-daily-sync-VoxScorecardsLive` — also live in
  this GCP project but belong to an unrelated Monday.com integration, not this
  pipeline.)

## Full schedule

All times are Mountain (`America/Denver`, handles MST/MDT automatically).
Every job's retry fires at **9:45 PM** and only does real work if that day's
scheduled run `failed` (a `success`/`partial` day makes it a silent no-op) —
but see the caution below the table.

| Category | Pipeline | Reports produced (email body lists each by this name) | Prod job | Prod time | Test job | Test time |
|---|---|---|---|---|---|---|
| **Sales** | `label_design` | Label Design Queue | `plex-etl-label-design` | 9:30 AM, 1:30 PM | `plex-etl-label-design-test` | 9:40 AM, 1:40 PM |
| **Sales** | `sales_orders` | 27 reports — see `bq_view` in `reports/sales_orders.yaml` | `plex-etl-sales-orders` | 7:00 PM | `plex-etl-sales-orders-test` | 7:10 PM |
| **Production** | `work_orders` | 19 reports — see `bq_view` in `reports/work_orders.yaml` | `plex-etl-work-orders` | 7:20 PM | `plex-etl-work-orders-test` | 7:30 PM |
| **Supply Chain** | `purchasing_open_orders` | Vox \| Open Purchase Orders, Purchase Orders to Approve: Results | `plex-etl-purchasing-open-orders` | 7:40 PM | `plex-etl-purchasing-open-orders-test` | 7:50 PM |
| **Supply Chain** | `part_obsolescence` | Vox \| Products to be Discontinued | `plex-etl-part-obsolescence` | 8:00 PM | `plex-etl-part-obsolescence-test` | 8:10 PM |
| **Supply Chain** | `inventory_activity` | Inventory Activity Detail Usage Per Month, Vox Scorecard \| Avg Daily Usage | `plex-etl-inventory-activity` | 8:20 PM | `plex-etl-inventory-activity-test` | 8:30 PM |
| **Inventory** | `inventory_snapshot` | Current Inventory Snapshot, Vox \| Inventory Valuation Summary, Vox Scorecard \| Inventory Value Total | `plex-etl-inventory-snapshot` | 8:40 PM | `plex-etl-inventory-snapshot-test` | 8:50 PM |
| **Quality** | `quality_nonconformance` | Quality Nonconformance, Turn Around Time Report, Quality Deviations, Vox Scorecard \| NC Cost by Category, Vox Scorecard \| NC Cost by Disposition (Destruction/Rework) | `plex-etl-quality-nonconformance` | 9:00 PM | `plex-etl-quality-nonconformance-test` | 9:10 PM |
| **Supply Chain** | `part_on_hand_inventory` | Part On-Hand Inventory, Inventory Risk Analysis, MFG Job Schedule - Inventory Availability (partial), Vox Scorecard \| Top Quantity Ranking, Vox Scorecard \| Cycle Count Accuracy | `plex-etl-part-on-hand-inventory` | 9:20 PM | `plex-etl-part-on-hand-inventory-test` | 9:30 PM |
| **Supply Chain** | `purchasing_pending_requisitions` | Vox \| Purchasing \| Pending Order Requisitions | `plex-etl-purchasing-pending-requisitions` | 9:40 PM | `plex-etl-purchasing-pending-requisitions-test` | 9:50 PM |
| **Sales** | `sales_quotes` | Open Quotes | `plex-etl-sales-quotes` | 10:00 PM | `plex-etl-sales-quotes-test` | 10:10 PM |
| **Sales** | `sales_returns` | Open RMA's | `plex-etl-sales-returns` | 10:20 PM | `plex-etl-sales-returns-test` | 10:30 PM |
| **Supply Chain** | `quality_supplier_returns` | Approve Vendor Return Authorizations | `plex-etl-quality-supplier-returns` | 10:40 PM | `plex-etl-quality-supplier-returns-test` | 10:50 PM |
| *all* | *retry* | — | `plex-<pipeline>-sync-retry` | 9:45 PM | `plex-<pipeline>-sync-test-retry` | 9:45 PM |

Prod/test pairs are staggered 10 minutes apart. `scorecard_goals_resolved` is
built by both `sales_orders` and `work_orders`, which is why the per-pipeline
view counts add up to 69 while there are 68 distinct views.

> **Caution — the 9:45 PM retry predates the late slots.** The retry was set
> 15 minutes after the *last* job back when the cascade ended at 9:30 PM. It
> now fires before `plex-etl-purchasing-pending-requisitions-test` (9:50 PM)
> and the six sales-quotes / sales-returns / quality-supplier-returns jobs
> (10:00–10:50 PM). And "today" in the retry check is the **UTC** date
> (`run_date` in `job_run_log`, `CURRENT_DATE()` in `main.py`), so Label
> Design's 9:30 AM / 1:30 PM runs land on the previous UTC day from its 9:45 PM
> retry. Reading `main.py`, a retry that finds no scheduled run "today" does a
> full run — so those nine jobs likely get an extra full run (and email)
> every night. Not yet confirmed against `job_run_log`; check before relying
> on the retry for those pipelines:
>
> ```sql
> SELECT job_name, run_mode, status, logged_at
> FROM `voxdatalake.PlexProd.job_run_log`
> WHERE run_mode = 'retry' AND status != 'skipped'
> ORDER BY logged_at DESC
> ```

**Changing a time:** Sales Orders' pair is `scheduler_cron`/`scheduler_cron_test`
in `terraform.tfvars`; every other job's `schedule` is a literal in
`terraform/main.tf`; the retry is `retry_scheduler_cron`. Commit, merge to
`main`, `./scripts/deploy.sh` — then update this table in the same commit.

## What "category" actually controls

As of the 2026-08-12/13 naming cleanup, every report config
(`reports/*.yaml`) declares a `category` and each of its `bq_view` entries
a `display_name`. `email_utils.py` uses these to build the subject —
**one subject per pipeline, identical for prod and test**. Since 2026-09-04
the subject is `[Plex ETL] - {Category}: {Pipeline} — {date}` (the pipeline
name, with a leading category word dropped) and the list of reports moved to
the body under "REPORTS PRODUCED" — the old subject enumerated every
`display_name` and reached 810 characters on `sales_orders`. E.g.:

```
[Plex ETL] - Production: Work Orders — 2026-09-25
[Plex ETL] - Quality: Nonconformance — 2026-09-25
[Plex ETL] - Sales: Label Design — 2026-09-25
```

The rest of this section and the dated sections below are the history of how
it got here.

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

## Real run history (job_run_log, as of 2026-08-13 — historical)

Queried directly against `PlexProd.job_run_log`/`PlexTest.job_run_log`
(excludes local-dev noise rows like `scratch_test_*.yaml` — those come from
`docker compose run` testing on this machine, never a real Cloud Run
execution, and use a different `job_name` key so they can't corrupt real
retry-skip logic):

- `plex-etl-sales-orders` / `plex-etl-sales-orders-test`: running since 2026-07-21, 23–26
  `success` rows each — the oldest, most stable jobs.
- `plex-etl-work-orders`: 23 `success` + **1 `failed`** (2026-07-21) — the
  one real example of the retry mechanism actually mattering in this
  dataset.
- The 6 newer NetSuite-parity jobs (purchasing, obsolescence, inventory
  activity/snapshot, quality nonconformance, part-on-hand): 1–4 rows each,
  all `success` — consistent with their 2026-08-10/11/12 deploy dates, not
  a sign of anything wrong.

## What changed 2026-08-13 (standardization — historical)

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
4. (Historical — manual `gcloud storage cp` into the prod paths is no longer
   done; see `OPERATIONS.md`.) Pushed the 5 new config files to GCS via `gcloud storage cp` (a
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

## What changed 2026-08-19 (historical)

> Historical record. Counts here are as of that date (8 pipelines, 16 jobs,
> 32 schedulers); the current picture is at the top of this page. The
> `terraform apply` runs described below predate `./scripts/deploy.sh` and the
> deploy guard (2026-09-25), which are now the only way to apply.

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
- ~~Renaming the legacy `plex-etl`/`plex-etl-test`/`plex-daily-sync` Sales
  Orders names~~ **Done 2026-09-04** (first rejected as not worth the
  destroy/recreate on 2026-08-13). They are now `plex-etl-sales-orders`,
  `plex-etl-sales-orders-test`, `plex-sales-orders-sync` and
  `plex-sales-orders-sync-test` — see CLAUDE.md "Job naming".
- ~~The image-tag cosmetic drift...~~ **Resolved 2026-08-13.** Every
  `google_cloud_run_v2_job` now has `lifecycle { ignore_changes = [image,
  client, client_version] }` — Terraform no longer tracks the deployed
  image at all, so it can't drift *or* get silently reverted by an
  unrelated `terraform apply`. `image_url` in `terraform.tfvars` is now
  always a pinned commit SHA (never `:latest`) and only matters for
  first-time job creation; `deploy/cloudbuild.yaml`'s single `deploy-all`
  step (all 26 jobs today, one loop) — or a manual `gcloud run jobs update
  --image=...`— is the only thing that ever moves a job onto a new image.
  Verified live: `terraform plan` shows `No changes` immediately after a
  real `gcloud run jobs update`, both right after adding the lifecycle
  block and again after a full rebuild+redeploy to commit `2f235d2`.
