# Changelog

All notable changes to this project are documented here, most recent first.

This is a continuously-deployed internal data pipeline, not a versioned
library — there are no release tags, so entries are grouped by date
instead of a version number. Within each date, changes are grouped using
the [Keep a Changelog](https://keepachangelog.com/) categories (**Added**,
**Changed**, **Fixed**, **Deprecated**, **Removed**, **Security**) wherever
they cleanly apply.

**Convention going forward:** every commit that changes behavior,
infrastructure, or a deployed report gets a matching entry here, added in
the same commit. Pure doc-typo fixes and this file's own housekeeping
don't need an entry.

## 2026-08-21

### Added
- **`part_product_type` column** on `mfg_job_schedule_report`,
  `part_on_hand_inventory_report`, and `inventory_risk_analysis_report` —
  joins `Part_v_Part.Product_Type_Key` to `Part_v_Part_Product_Type`
  (already extracted, never previously used by any report). This is a
  real, already-populated (64/80 live parts) classification with 49
  configured values — Vitamin, Mineral, Botanical Extract, Stock vs Custom
  Formula Blend/Capsules, Blank/Custom/Labeled Bottle, Product/Fancy/
  Outsourced Label, etc. — far more useful than `Part_v_Part.Part_Type`
  (inline text, generically "Raw Materials" for nearly everything).
  Directly resolves the Stock-vs-Custom question that `mfg_job_schedule_report`
  had only speculative proxies for — confirmed live: two "White Bottle"
  parts classify as "Blank Stock Bottle," the "Black Bottle" variant of the
  same product classifies as "Custom Blank Bottle."
- `sales_orders_pending_approval_by_rep_report` — "Orders Pending Approval
  by Sales Rep," built as a thin alias view over
  `sales_orders_pending_approval_report` (decided to be the same
  underlying data under NetSuite's alternate label, not a genuinely
  distinct search — see `docs/NETSUITE_PARITY_OPEN_ITEMS.md`).
- `is_at_risk` boolean on `inventory_risk_analysis_report` — 90+ days
  since last container activity (or no activity at all). First real aging
  threshold on this report; `days_since_activity` stays exposed so the
  cutoff can change with zero recomputation if 90 is wrong for this
  business.
- `sales_orders_rush_open_report` — "Vox | RUSH Open Sos" / "One for Rush
  orders," unblocked by screenshots of the real NetSuite search. The
  `Sales_v_Priority` lead (0 rows live) was a dead end because it was the
  wrong lead: the actual criterion is `Memo (Main) contains RUSH`, a
  free-text convention confirmed on a real order. Built as
  `UPPER(Sales_v_PO.Note) LIKE '%RUSH%'` plus a status exclusion (Closed/
  Cancelled/Pending Sales Approval) — see `sales_orders_rush_open_view.sql`
  for the "Billed" status gap (no Plex equivalent) and the unconfirmed
  Note-field-convention caveat.
- `sales_order_allocation_report` — "Vox | Allocation Report," unblocked
  by a screenshot of the real search after being "no match found." Joins
  `Sales_v_PO -> Sales_v_PO_Line -> Sales_v_Release -> Sales_v_Release_Job
  -> Part_v_Job` (new extraction: `Sales_v_Release_Job`; `Part_v_Job`/
  `Part_v_Job_Status` read as shared tables already extracted by the
  `work_orders` pipeline, same cross-pipeline pattern as `Part_v_Part`).
  Of NetSuite's 4 sales-order statuses in the filter, only "Pending
  Fulfillment" is confirmed live on this tenant — decided to use the same
  "not Closed/Cancelled" open-status proxy already used for Open Quotes/
  RMAs rather than build on the one narrow match. Job side uses the same
  Completed/Cancelled/Hold-inverse pattern as the Labeling/Printing Open
  WO reports.

### Changed
- **Resolved the entire "needs data-scientist input" backlog** in
  `docs/NETSUITE_PARITY_OPEN_ITEMS.md` Part 1 (11 reports) — Emilio's call
  to pick best-criteria answers now rather than wait, adjustable later if
  real data (starting 2026-08-24) shows a report is wrong. Only one real
  code change beyond the two above: `sales_quotes_open_report` now treats
  "Approved" as closed, not open (a quote past approval is moving toward
  becoming an order, not still awaiting a decision) — every other item
  kept its existing best-guess default, now documented as a decision
  instead of an open question. `Vox | RUSH Open Sos` was the one exception
  still blocked at the time — resolved later the same day once real search
  criteria surfaced (see the Added entry above).
- Test emails **decided to stay as-is** — all 3 recipients
  (`emilio.dominguez@`/`jennilyn.tockstein@`/`marketing@parasolgroupinc.com`)
  continue getting test-environment emails; the "worth deciding" item in
  `docs/EMAIL_SCHEDULE.md` is closed.
- SendGrid domain authentication confirmed working — the "couldn't verify"
  Gmail warning is no longer a live concern.

### Fixed
- 4 more stale "runs at 2/3 AM" schedule comments in `work_orders.yaml`/
  `part_on_hand_inventory.yaml`/`quality_nonconformance.yaml` (prod + test)
  that the 2026-08-19 doc sweep didn't catch, since they're code comments
  inside yaml files, not doc files.

### Flagged, not resolved
- NetSuite's "Sample Order" custom body field — confirmed manual/
  NetSuite-only (Field Help: "custom field created for your account," no
  source formula; `Sales_v_PO_Type` has no "Sample" type configured; real
  order pricing is inconsistent, ruling out a price-based proxy). Logged
  in `reports-list/sales.md` with options if this becomes a priority
  (Google Sheet bridge, a real Plex "Sample" order type going forward, or
  a NetSuite-native SuiteAnalytics Connect data source if this pattern
  recurs across other reports).

## 2026-08-19

### Added
- `quality_deviation_report` — 3rd `bq_view` on the existing
  `plex-etl-quality-nonconformance(-test)` job. Correlates Quality
  Deviations to Jobs/Problems/Parts/Workcenters via `Quality_v_Deviation`
  and 4 junction tables (`_Job`/`_Problem`/`_Part`/`_Workcenter`) plus 2
  lookups (`_Type`/`_Status`) — the resolution to the long-standing
  "NC-to-job correlation has no FK" gap flagged since 2026-08-11/12. See
  `catalog/plex_quality_views_catalog.md` "Deviations" section for the
  schema discovery.
- `CHANGELOG.md` (this file).

### Changed
- **All 32 Cloud Scheduler jobs** (16 main + 16 retry, across all 8 report
  categories) moved from scattered UTC times (2 AM–5 PM UTC for main jobs,
  a fixed 6 AM Mountain for every retry) to a single 7:00 PM–9:45 PM
  Mountain (`America/Denver`) cascade, 10 minutes apart — specifically so
  nothing lands as an early-morning/odd-hour email. `scheduler_time_zone`
  changed from `"UTC"` to `"America/Denver"`; every per-category `schedule`
  literal in `terraform/main.tf` recomputed; `retry_scheduler_cron` moved
  from `"0 6 * * *"` to `"45 21 * * *"`. Full new schedule documented in
  `docs/EMAIL_SCHEDULE.md`.
- 12 documentation files updated to match the new schedule (`CHEATSHEET.md`,
  `OPERATIONS.md`, `DEPLOYMENT_GUIDE.md`, `TECHNICAL_REFERENCE.md`,
  `QUICKSTART.md`, `FRONTEND_GUIDE.md`, `TEARDOWN.md`, `API_REFERENCE.md`,
  `CLICKUP_TEAM_GUIDE.md`, `README.md`, plus dated addenda — not rewrites —
  on the historical `NETSUITE_REPORT_BUILD_PLAN.md` and
  `MFG_JOB_SCHEDULE_BUILD_PLAN.md`).
- 10 reports-list catalog rows (`reports-list/sales.md` ×6,
  `supply-chain.md` ×2, `production.md` ×2) flipped from "scaffolded, not
  yet deployed" to "✅ Deployed" now that their SQL is confirmed live —
  the caveats about unconfirmed business-rule criteria were kept, since
  deployment status and business-rule correctness are separate questions.

### Fixed
- **12 previously-written `bq_view` SQL files were silently never
  deployed.** Terraform only pushes a GCS bucket-object for a SQL file if
  an explicit `google_storage_bucket_object` resource exists for it — it
  does not infer new files from a yaml's `bq_view` list. Every time a new
  view got added to an already-deployed report's yaml without a matching
  Terraform resource, the SQL sat in the repo but never reached GCS.
  `quality_turnaround_time_report` had been broken this way since
  2026-08-14, unnoticed until now. Fixed: uploaded all 12 files, added the
  12 missing Terraform resources (`terraform apply`: 12 added, 0 changed).
- `quality_deviation_view.sql` compared an `INT64`-cast join key against a
  bare `STRING` key — `raw_Part_v_Job` and `raw_Quality_v_Problem` are
  currently empty (real data starts loading 2026-08-24), so BigQuery typed
  their key columns as STRING. Fixed with symmetric `SAFE_CAST` on both
  sides of every join, not just one.
- `mfg_job_schedule_view.sql`: real data just started landing in
  `Part_v_Lot_Shelf_Life`, revealing the column is actually typed
  `DATETIME`, not the numeric duration originally guessed —
  `SAFE_CAST(... AS FLOAT64)` has no defined cast path from DATETIME at
  all, so it failed even with SAFE_CAST (same "no valid cast pair" class
  of bug as the `SAFE_CAST(INT64 AS DATE)` gotcha from 2026-07-15, a
  different type pair). Fixed by passing the value through as raw STRING
  instead — its business meaning is still unconfirmed, this only stops
  the crash.
- Verified end-to-end, not just planned: every one of the 8 categories'
  test jobs was actually executed post-fix and its views confirmed
  building with no errors.

## 2026-08-11 to 2026-08-13 — NetSuite parity build-out, naming standardization

### Added
- 4 new NetSuite-parity Cloud Run jobs: purchasing open orders, part
  obsolescence, inventory activity, inventory snapshot (+ inventory
  valuation summary as a 2nd `bq_view`).
- `quality_nonconformance_report` (`Quality_v_Problem`) and
  `part_on_hand_inventory_report` (`Part_v_Container`) — 2 more new jobs.
- `mfg_job_schedule_report` and `labeling_open_work_orders_report` — added
  as sibling `bq_view`s on the existing work_orders job, requiring no new
  Cloud Run resources. All 10 tabs of the source "MFG Job Schedule" Google
  Sheet mapped to Plex ODBC views (see `spreadsheets/mfg_job_schedule.md`).
- Full column-level schema catalog extracted for all 2,828 live Plex ODBC
  views (`catalog/full_schema_catalog.csv`).
- `reports-list/` — company-wide report inventory catalog (NetSuite,
  DataNinja, Monday.com, Excel, Google Sheets), cross-referenced against
  what this pipeline can actually build from Plex.
- Every `bq_view` entry can now carry a `display_name`, and every report
  config a `category` — used to build accurate, per-report email subjects
  instead of a generic pipeline-level one.

### Changed
- Environment (PRODUCTION/TEST) moved out of the email subject entirely
  (derived from `BQ_DATASET`, shown only as a body badge) so a category's
  prod/test subjects are byte-identical.
- Total Cloud Run jobs: 4 → 15 over this stretch.

## 2026-07-19 to 2026-07-21 — Production stabilization

### Added
- Plain-English error hints for known Plex/ODBC error codes in failure
  emails.
- Failure-retry mechanism: every job gets a second Cloud Scheduler trigger
  (`*-retry`) that re-invokes it with `RUN_MODE=retry`, checking a new
  `job_run_log` BigQuery table so only a genuinely FAILED run gets retried
  (fired daily at 6 AM Mountain at the time — see 2026-08-19 above for
  where this moved to).

### Fixed
- Production ODBC outage (error 2404, "Session refused by service")
  resolved by Plex Support — an account-level session restriction, not a
  network/driver/code issue (two-network reproduction ruled out network
  causes first).
- Migrated off `gsutil` to `gcloud storage` ahead of Google's deprecation.
- Terraform state migrated from local-only (`terraform.tfstate`, gitignored
  — a single point of failure) to a versioned GCS backend.
- Stale project ID / dataset / table names and inverted prod↔test ODBC
  host labels corrected across the docs a new teammate would read first.

## 2026-07-13 to 2026-07-14 — Multi-report architecture, code review

### Added
- `work_orders_report` pipeline (job/op/workcenter/hours), the first
  report alongside the original `sales_orders_report`.
- Partial-failure tracking and 0-row warnings in the ETL pipeline.

### Fixed
- All critical/high findings from a full code review
  (`docs/CODE_REVIEW_2026-07-14.md`).
- Plex nanosecond INT64 date columns now convert to real BigQuery DATE
  values in both view SQLs, with zero-sentinels (`1970-01-01`) mapped to
  NULL — discovered `SAFE_CAST(INT64 AS DATE)` is an invalid cast *pair*
  (a compile-time error, not a runtime one), so every date conversion now
  routes through `CAST(col AS STRING)` first, which is legal from any type.
- Email subject/context now correctly distinguishes which pipeline/report
  produced a given run.

## 2026-06-29 — GCS-backed multi-report pipeline

### Added
- Report configuration (Plex view, filter, JOIN SQL) moved out of hardcoded
  Python into per-report YAML + SQL files loaded from a GCS bucket at
  runtime — editable without a container rebuild or `terraform apply`.

## 2026-05-15 to 2026-06-18 — Initial build

### Added
- Original Plex → BigQuery ETL pipeline: ODBC extraction, Terraform
  infrastructure (Cloud Run, Cloud Scheduler, Secret Manager, Artifact
  Registry), SendGrid email reporting, and the initial documentation set
  (README, QUICKSTART, DEPLOYMENT_GUIDE, OPERATIONS, TECHNICAL_REFERENCE,
  FRONTEND_GUIDE, API_REFERENCE, TEARDOWN, CHEATSHEET).
