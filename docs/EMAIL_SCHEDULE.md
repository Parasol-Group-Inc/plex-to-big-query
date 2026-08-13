# Email & Schedule Reference

Full inventory of every Cloud Run Job that emails a report, when it runs,
what it's actually made of, and who hears about it. Built 2026-08-13 while
standardizing report naming across the whole pipeline (see
[OPERATIONS.md](OPERATIONS.md) for the retry mechanism this depends on).

## The short version

- **16 Cloud Run Jobs** (8 report pipelines × prod/test), each running once
  a day, each sending exactly one email per run.
- **Baseline: 16 emails/day** if nothing fails. A failed run adds a second
  email that same day (its own failure notice + the 6 AM Mountain retry's
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

All times UTC unless noted. Retry only fires *real* work (and a second
email) if that day's scheduled run status was `failed` — a `success` or
`partial` day makes the retry a silent no-op, no email sent. Retry itself
always fires at the same instant for every job: `6 AM America/Denver`
(handles MST/MDT automatically).

| Category | Reports produced (email body lists each by this name) | Prod job | Prod time | Test job | Test time |
|---|---|---|---|---|---|
| **Sales** | Sales Orders, Vox \| Open Sales Orders | `plex-etl` | 2 AM | `plex-etl-test` | 3 AM |
| **Production** | Work Orders, MFG Job Schedule, Labeling \| Open WO: Results | `plex-etl-work-orders` | 4 AM | `plex-etl-work-orders-test` | 5 AM |
| **Supply Chain** | Vox \| Open Purchase Orders | `plex-etl-purchasing-open-orders` | 6 AM | `plex-etl-purchasing-open-orders-test` | 7 AM |
| **Supply Chain** | Vox \| Products to be Discontinued | `plex-etl-part-obsolescence` | 8 AM | `plex-etl-part-obsolescence-test` | 9 AM |
| **Supply Chain** | Inventory Activity Detail Usage Per Month | `plex-etl-inventory-activity` | 10 AM | `plex-etl-inventory-activity-test` | 11 AM |
| **Inventory** | Current Inventory Snapshot, Vox \| Inventory Valuation Summary | `plex-etl-inventory-snapshot` | 12 PM | `plex-etl-inventory-snapshot-test` | 1 PM |
| **Quality** | Quality Nonconformance | `plex-etl-quality-nonconformance` | 2 PM | `plex-etl-quality-nonconformance-test` | 3 PM |
| **Supply Chain** | Part On-Hand Inventory | `plex-etl-part-on-hand-inventory` | 4 PM | `plex-etl-part-on-hand-inventory-test` | 5 PM |

Prod/test pairs are staggered exactly 1 hour apart, on the hour, 2 AM
through 5 PM — this pattern was already consistent before today's
naming work; nothing needed fixing here.

## What "category" actually controls

As of the 2026-08-12/13 naming cleanup, every report config
(`reports/*.yaml`) declares a `category` and each of its `bq_view` entries
a `display_name`. `email_utils.py` uses these to build the subject —
**one subject shape per category, identical for prod and test** — e.g.:

```
[Plex ETL] Production: Work Orders, MFG Job Schedule, Labeling | Open WO: Results — SUCCESS — 2026-08-13
[Plex ETL] Quality: Quality Nonconformance — SUCCESS — 2026-08-13
```

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
4. Pushed the 5 new config files to GCS via `gcloud storage cp` (Terraform
   apply wasn't available in that session) — functionally identical to a
   Terraform-applied upload, but it sets `content_type: text/plain` where
   Terraform's own uploads leave `application/octet-stream`. That attribute
   is `ForceNew` on `google_storage_bucket_object`, so `terraform plan` now
   shows those 5 report configs (prod+test = 10 objects) as **replace**, not
   update. Harmless — content is correct and confirmed live — but real
   drift. Fix properly by either pinning `content_type` explicitly on these
   resources in `terraform/main.tf`, or by making `terraform apply` the only
   sanctioned way to push a report config edit (never `gcloud storage cp`
   directly). Not yet fixed.

## Worth deciding (not changed — needs a call, not a guess)

- **Test runs email the same 3 real people as prod**, including
  `marketing@parasolgroupinc.com`. That's 8 "TEST" emails a day to an
  inbox that presumably doesn't need to see test-environment noise. Options:
  a dedicated test-only recipient (e.g. just Emilio), or suppress
  `SENDGRID_ENABLED` on test entirely and rely on the Cloud Console/logs for
  test verification. Either is a one-line `terraform.tfvars` change once
  decided.
- **Renaming `plex-etl`/`plex-etl-test`** to match the newer
  `plex-etl-{report}` pattern was considered and **rejected as not worth
  it** — Cloud Run Job names are immutable, so this would mean Terraform
  destroying and recreating the job (losing execution history) plus
  updating `cloudbuild.yaml`'s `_CR_JOB` substitution and the scheduler
  target. Real risk for a purely cosmetic gain, given naming already reads
  fine in context (it's the original/sales-orders job, predates the
  `-work-orders`/`-inventory-snapshot` naming convention).
- The image-tag cosmetic drift (`:f46d93e` vs. Terraform's declared
  `:latest`) noted in `docs/DEPLOYMENT_STATE`-style memory still applies to
  all 16 jobs now, not just the original 2 — same digest either way,
  deliberately left unresolved pending a decision on which deploy mechanism
  (Cloud Build's SHA-pinning vs. Terraform's `:latest`) should be the
  source of truth.
