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

## 2026-09-04

### Added — goals now have a home, and every "% to Goal" tile is buildable
The biggest open item on the scorecard is closed. Goals live in a Google Sheet
(where people can actually edit them) and reach BigQuery via an Apps Script.

- **`scorecard_goals` table created by hand in `PlexTest` and `PlexProd`.**
  **Not managed by Terraform, not created by the ETL** — the pipeline only
  reads it. Long format, one row per `(metric, period_month, scope)`, because
  the three grains genuinely differ: revenue is company-wide, sales goals are
  per rep, production goals are per work centre group. A wide table couldn't
  hold all three without NULL-padding or three tables to keep in sync, and
  long format makes a new metric a new row rather than a schema migration plus
  an Apps Script edit. Full column list and rebuild DDL in
  `docs/reports/scorecard_goals.md`.
- **`deploy/goals_sheet_to_bigquery.gs`** — the Apps Script. `WRITE_TRUNCATE`
  so the sheet is the single source of truth (an append-only load would
  accumulate duplicate goals for a month and quietly double every tile);
  **refuses to push an empty sheet**, which would otherwise blank every goal
  tile; declares its schema rather than autodetecting, since autodetect on a
  month of round numbers lands `goal_value` as INTEGER and breaks the next
  push containing a decimal; skips and logs bad rows instead of failing the
  whole load.
- **Three new `bq_view`s**, each kept inside a single pipeline so neither
  depends on a view the other creates:
  - `revenue_vs_goal_report` (`sales_orders.yaml`) — LEFT JOIN on purpose, so
    a month with revenue but no goal yet still shows rather than the tile
    vanishing because somebody hasn't filled in next month.
  - `sales_vs_goal_report` (`sales_orders.yaml`) — FULL OUTER JOIN, so a rep
    with a target and no sales yet shows at 0%. That's the case someone is
    actually checking at the start of a month; an inner join hides it.
  - `production_vs_goal_report` (`work_orders.yaml`) — same reasoning.
- **All three deployed and verified in BOTH datasets**, by querying each view
  directly rather than trusting job exit codes. `PlexTest`: Bottling **3,000 of
  5,000 (60%)**, Pre-Weigh **429 of 1,000 (43%)**, September revenue $65 against
  a $200,000 placeholder, and **0 unmatched scope names** on either the rep or
  work-centre-group join — the exact-string-match trap is not currently biting.
  `PlexProd`: all three exist and return 0 rows, correct on both counts since it
  has neither actuals nor goals yet.
- 4 placeholder rows seeded in `PlexTest` only, every one noted `PLACEHOLDER —
  replace from the sheet`; the first real Apps Script push replaces them.
  `PlexProd.scorecard_goals` left empty.

### Found — the scope join is an exact string match, and Plex disagrees with the tile names
- **Plex's work centre group is `Encapsulating`; the scorecard tile says
  "Encapsulation".** A mismatch produces a NULL goal, not an error, so it
  would read as 0% forever with nothing indicating why. All three views
  therefore expose `goal_without_sales` / `goal_without_production` flags to
  surface an unmatched goal row rather than letting it sit invisible. Same
  trap applies to rep names, including the literal `(no rep assigned)` bucket
  that unassigned orders collapse into.

### Changed — email subjects cut from 810 characters to ~45
- **`[Plex ETL] - {Category}: {Pipeline} — {date}`**, e.g.
  `[Plex ETL] - Sales: Orders — 2026-09-04`.
  The subject used to enumerate every `display_name` the run produced. That was
  fine at 2-3 reports per pipeline and became unusable once the scorecard work
  pushed `sales_orders` to 22 views: the real subject line hit **810
  characters**, wrapped over four lines in Gmail, and buried the one word that
  identifies the email. Longest subject is now **71 characters**, most are
  under 60. The full report list still ships in the body under "REPORTS
  PRODUCED", where it can actually be scanned. Removed the now-unused
  `display_names` local in `email_utils.py`.
- **Category alone was not enough, so the pipeline name is included.** An
  intermediate version used category only and was rejected on inspection:
  "Supply Chain" is shared by six pipelines (`inventory_activity`,
  `part_obsolescence`, `part_on_hand_inventory`, `purchasing_open_orders`,
  `purchasing_pending_requisitions`, `quality_supplier_returns`) and "Sales" by
  three, so six jobs would have arrived looking identical with the body's
  report list the only way to tell which had run. **Verified all 12 pipelines
  now produce distinct subjects.**
- **A leading category word is stripped from the pipeline name** so the common
  cases don't stutter: `Quality: Nonconformance` rather than "Quality: Quality
  Nonconformance", `Sales: Orders` rather than "Sales: Sales Orders". Exact
  leading-word match only, and never trimmed to nothing — a pipeline named
  exactly after its category keeps its full name instead of becoming
  "Quality: ".
- **Prod and test still share a subject, unchanged and deliberate.** The
  `_test` suffix is stripped so the two environments thread together rather
  than forking into separate-looking emails; PRODUCTION/TEST shows as a badge
  in the body. That's why 24 jobs produce 12 distinct subjects, not 24.
- **`run_date` deliberately kept.** Without it, every day's run for a pipeline
  collapses into one ever-growing Gmail thread, making a specific day's email
  materially harder to find. One line to remove if that's actually wanted.
- **⚠ Ships via Cloud Build, not `terraform apply`** — this is a code change to
  `email_utils.py`, baked into the container image. A Terraform apply will not
  pick it up.
- **DEPLOYED 2026-09-04.** Cloud Build `0113e1f1` succeeded and its `deploy-all`
  step moved **all 24 Cloud Run jobs** to `etl:6c33c51`. Confirmed the final
  code is in that image: `email_utils.py` was last written 22:58 UTC, the build
  was created 23:09 UTC, and there is no `.gcloudignore`, so the whole working
  tree was uploaded.
- **Provenance wrinkle, recorded not hidden:** the image is tagged `6c33c51`
  but contains changes that were still uncommitted when it was built (they are
  now in `15cded9`). The tag is a `git rev-parse` label taken at submit time,
  not a guarantee of what went in. **The next build from a clean tree makes the
  tag truthful again** — no action needed unless you're tracing which commit
  produced a running image, in which case treat `6c33c51` as "at least
  6c33c51".

### Changed — `terraform.tfvars` housekeeping (gitignored, not in this commit)
- **`image_url` bumped again, `:8ba5717` → `:6c33c51`**, matching what the
  Cloud Build run actually left on the jobs. This variable drifted **twice in
  one day**, which is the point: `lifecycle.ignore_changes` on `image` lets the
  live jobs run ahead of it by design, and it only matters when a rename
  destroys and recreates a job — that job comes up on this value. The comment
  block now says how to re-check it rather than narrating one past bump.
- Corrected the stale `report_subject` comment, which still described the old
  enumerate-every-report subject format.
- **Backed up to `gs://voxdatalake-terraform-state/plex-to-big-query/terraform.tfvars.backup`**,
  the path the file's own header documents. Bucket versioning confirmed
  enabled, so earlier copies stay recoverable. Contains no secrets — only
  Secret Manager *identifiers* (`plex-access-token` etc.), never values.

### Changed — renamed the Sales Orders job off its legacy generic name
- **`plex-etl` → `plex-etl-sales-orders`** and **`plex-etl-test` →
  `plex-etl-sales-orders-test`**; schedulers **`plex-daily-sync` →
  `plex-sales-orders-sync`** (`-test`/`-retry` variants follow automatically,
  since they derive from `var.scheduler_job`).
  Sales Orders was the *only* pipeline when it was built, so it took the
  generic name and kept it after the repo went multi-report. Every other
  pipeline is `plex-etl-<pipeline>` / `plex-<pipeline>-sync`, so
  `gcloud run jobs execute plex-etl-sales-orders-test` — the obvious guess —
  failed with `NOT_FOUND`. Same for `plex-daily-sync`, which sounds global but
  only ever triggered sales orders. This rename was already logged as a TODO
  in `docs/EMAIL_SCHEDULE.md`.
  Touched: `terraform/terraform.tfvars`, `terraform/variables.tf`,
  `deploy/cloudbuild.yaml` (**both** `_CR_JOB_TEST` and `_ALL_JOBS` — a job
  missing from that list silently never gets a new image again),
  `deploy/setup.sh`, `reports/test/sales_orders.yaml`, and 11 operational
  docs. `CHANGELOG.md` and the dated `CODE_REVIEW_*` docs were deliberately
  left alone — they're a historical record of names that were real at the time.
  Plan is exactly **6 to add, 1 to change, 6 to destroy**: the 2 Cloud Run
  jobs + 4 schedulers, all replacements. Both resource types have immutable
  names, and neither holds state.

### Fixed — `image_url` had silently gone stale, and the rename would have shipped it
- **`image_url` bumped `:2f235d2` → `:8ba5717`.** Every job's
  `lifecycle.ignore_changes` on `image` lets the live jobs drift ahead of this
  value by design, so it had fallen several deploys behind — all live jobs
  were verified running `:8ba5717` while tfvars still said `:2f235d2`.
  Normally that's harmless. **It is not harmless during a rename**: Terraform
  destroys and recreates the renamed jobs, and a recreated job is a brand-new
  job, so it comes up on whatever `image_url` says. Applying the rename
  without this bump would have quietly rolled the Sales Orders pipeline back
  to an older image, with nothing in the plan output indicating it. Caught by
  diffing `gcloud run jobs describe` against tfvars before applying.

### Added — buildable-now scorecard items from the Sep 1 requirements meeting
Everything the Emilio/Jennilyn meeting (`meetings-reference/Sep-1/`) asked for
that nothing was actually blocking. **Five new `bq_view`s, zero new
extractions, zero new Plex ODBC calls** — every one reuses raw tables this
pipeline was already pulling. Not yet deployed (`gcloud` reauth is expired,
see Known friction in `CLAUDE.md`).

- **`sales_mtd_by_status_change_report`** + **`sales_mtd_summary_report`**
  (`reports/sales_orders.yaml`) — "Sales MTD" as Jennilyn actually defined it:
  every order line whose order first entered **Pending Fulfillment** in a
  given month, dated by the status change, with the sales rep retained.
  *"Anything that moved into pending fulfillment status during that month is
  our sales month to date... it's the date of that status change, not the date
  of the order."*
  **This turned out to need no investigation at all.** `Sales_v_PO_Change` was
  already being extracted, and `sales_orders_report` has been computing
  exactly this ("Date Approved" = `MIN(Change_Date)` where
  `PO_Status_Key = 2073`) in production since long before the scorecard
  effort started. Status key 2073 = "Pending Fulfillment" is confirmed live on
  this tenant, not inferred — the full workflow is documented in
  `catalog/plex_catalog_index.md`.
  Deliberately a **different number from Revenue**, which is shipped units out
  of the Shipping module. Jennilyn was explicit these are not interchangeable.
- **`sales_revenue_run_rate_report`** — MTD revenue against days elapsed, plus
  the straight-line projection to month end. Serves the "94% into month"
  sub-metric and the MTD Run Rate tile. Pure calendar arithmetic over
  `sales_revenue_summary_report`; no new data. Uses calendar days, matching
  the existing scorecard's own `pct_into_month` field — flagged in case Vox
  means business days.
- **`pipeline_plex_value_report`** — the Plex half of Total Pipeline: orders in
  a Quote status or Pending Sales Approval, with dollar value.
  **Reading Jennilyn's words literally avoided a whole extraction.** She said
  *"the sales **orders** that have the status quote"* — an order status
  (`Sales_v_PO_Status.Is_Quote`), not `Sales_v_Quote`, which is a separate
  object with its own workflow. Building on the Quote module instead would
  have meant extracting Plex's automotive quote-pricing tables
  (`Sales_v_Quote_Price`, with `Escalation_Year`/`IRR`/`NPV`/`EBITDA` and
  `Sales_v_Quote_Part.Die_Cavity_Count`) that a supplement manufacturer almost
  certainly never populates. Confirmed by reading the schema catalog before
  writing any SQL.
- **`production_monthly_by_workcenter_group_report`**
  (`reports/work_orders.yaml`) — *"production by work center group by month,"*
  every group at once. Complements rather than replaces the 4 Daily Reports,
  which are per-day/per-workcenter and each hardcode one group. Also
  structurally immune to the `Part_v_Job_Op` join bug fixed on 2026-09-01:
  it needs neither Job nor Part, so it never makes that join.

### Changed — WIP ambiguity resolved into data instead of a debate
- **`sales_order_value_by_status_report`** gained `status_key`,
  `is_pending_fulfillment` and `also_counts_in_pipeline` columns. Jennilyn
  defined WIP two different ways in the same conversation — the broad *"not a
  quote, not cancelled, not shipped"* and the strict *"anything that is
  pending fulfillment"* — and they do not produce the same number, because the
  broad reading also sweeps in Pending Sales Approval and Deposit Review.
  Rather than pick one and hope, the view keeps the broad reading and exposes
  a flag so the strict figure is one filter away. `also_counts_in_pipeline`
  marks the rows that **double-count against Total Pipeline**, which counts
  the same Pending Sales Approval orders — surfaced in both reports rather
  than silently netted, since which tile owns those dollars is a business
  call.

### Added — `docs/CHEATSHEET.md` reference section
- New **"Reference — Status Codes, Conventions & Business Rules"** section,
  written because the same facts had been re-derived from scratch in three
  separate sessions. Covers: the **`-1` vs `1` boolean split** (the single
  most expensive gotcha here — `Part_v_*` uses `-1 = true`, `Sales_v_*`
  status lookups use `1 = true`, and guessing wrong yields a permanently
  empty view that never errors), the full Sales Order and Quote status key
  tables, the four **distinct** Vox scorecard metric definitions (Revenue vs
  Sales MTD vs WIP vs Total in Shipping — not interchangeable), the
  out-of-stock rule, the mandatory date-conversion pattern, the
  `SAFE_CAST`-both-sides rule, and the list of things Plex genuinely cannot
  produce.

### Notes
- All 5 new views **dry-run clean against `PlexTest`** (`bq query --dry_run`).
  `sales_mtd_summary_report` correctly fails dry-run only because its source
  view doesn't exist yet — it resolves once deployed in list order.
- Real data confirmed present for the new Sales MTD path before building:
  `raw_Sales_v_PO_Change` has 39 rows, 3 of them at `PO_Status_Key = 2073`
  across **2 distinct orders** — so this returns real rows, not zero.
- `terraform validate` passes; `terraform fmt` clean. `terraform plan` shows
  **18 to add, 2 to change, 9 to destroy** — every one of those 9 is a GCS
  object *replacement* (destroy + recreate with new content), not a real
  deletion. The plan also picks up the 2026-09-01 shipping views, which were
  pushed manually and never tracked in Terraform state, so applying syncs
  **prod** as well and fixes the Daily Reports still broken there.
- **Applied.** All 5 new SQL files confirmed in
  `gs://voxdatalake-report-configs/sql/`, and the 2026-09-01 shipping views
  are now properly tracked in Terraform state rather than existing only as
  manual `gcloud storage cp` pushes.
- **`plex-etl-work-orders-test` ran; `production_monthly_by_workcenter_group_report`
  confirmed created** by querying `INFORMATION_SCHEMA.VIEWS` directly.
- **All 4 new `sales_orders` views deployed and verified.** The rename was
  applied, `plex-etl-sales-orders-test` executed successfully, and every view
  was queried directly rather than trusting the exit code:
  - `sales_mtd_by_status_change_report` — 10 lines, **7 real orders**, 35,201
    units, September 2026. The status-change mechanism works as designed.
  - `sales_mtd_summary_report` — 1 rep, September 2026.
  - `sales_revenue_run_rate_report` — September at **$65**, straight-line
    projection **$488**.
  - `pipeline_plex_value_report` — **$900,975 across 15 orders, 32 lines**,
    every one in Quote status (nothing sits in Pending Sales Approval on this
    tenant right now).
  - `sales_order_value_by_status_report` — `is_pending_fulfillment` and
    `also_counts_in_pipeline` are live. **All 10 WIP rows are Pending
    Fulfillment and 0 overlap with Pipeline**, so the broad and narrow WIP
    readings currently return identical rows — the ambiguity is real but
    costs nothing today.

### Found — the missing prices are specific to Pending Fulfillment orders
- **WIP and Sales MTD both read $0** despite 7 real orders and 35,201 units,
  because not one of those order lines has a matching row in
  `Part_v_Customer_Part_Price`. This is **not** a broken join or a wrong tier
  rule: quote-stage orders price correctly through the same code path
  (`pipeline_plex_value_report` returns $900,975, with only 2 of 32 lines
  missing a price). Whatever is absent is specific to the parts on these
  particular orders. Two scorecard tiles read $0 until a price source is
  agreed — raised with the data scientist rather than papered over with a
  guessed fallback.

### Note — `PlexTest` figures churn; don't quote them as business numbers
- **The 2026-09-01 test figures are gone.** The tenant's practice data was
  rebuilt between then and 2026-09-04: shipping revenue $25,500 → **$65**,
  ready-to-ship $115,800 → **$413**, open caps 4,643,140 → **2,226,500**, and
  `bottling_job_open_report` 0 rows → **4 open jobs**. Nothing regressed; the
  views are unchanged. Treat any earlier session's test numbers as stale.
- **`PlexProd` is still effectively empty** — checked 2026-09-04, every
  production view returns 0 rows except `sales_order_value_by_status_report`
  and `sales_orders_pending_approval_report` (2 orders each, no prices). Prod
  fills at go-live; the 4 new views land there on its next scheduled run.

## 2026-09-01

### Changed — corrected per the Emilio/Jennilyn scorecard-requirements meeting
- **Discovered this morning's Revenue/WIP/"Total in Shipping" builds were on the wrong Plex module entirely**, by reviewing `meetings-reference/Sep-1/` (Otter + Gemini transcripts of the actual requirements meeting with Jennilyn Tockstein, the data scientist). Jennilyn was explicit and repeated: "the shipping revenue should just be the units that went out the door... I think we want to pull it from the shipping [module]... the sales one I think will be less reliable since it will not count in when we like close things short or ship partials." Everything built earlier today against `Sales_v_PO`/`Sales_v_Release` order value was the wrong source for these three tiles specifically (Sales MTD-by-status-change logic and the 4 Daily Report fixes were unaffected — those matched the meeting exactly).
- **Found the real Plex module — tree-confirmed via `catalog/full_schema_catalog.csv`, then live-confirmed the same session**: `Sales_v_Shipper`/`_Line`/`_Status`/`_Container`/`_AR_Invoice`/`_Line_Release`, none ever extracted by this pipeline before. Independently corroborated by `mapping/enabled-reports.md`: "Customer Shipping History Summary" and "Shipper History Summary by Part Group" are literally enabled Plex UI reports on this tenant, under Sales and CRM — Plex ships a canned report for almost exactly what Jennilyn described. Added all 6 views plus `Sales_v_Release_Allocation` (for the Out-of-Stock rule) as new extractions on `reports/sales_orders.yaml`, deployed, and verified with real data: 2 real shipments, one actually Shipped (17,000 units × $1.50 = $25,500, reconciling exactly against 17 real `Sales_v_Shipper_Container` rows), one still Open with 20,000 ready units. Real bug caught by checking live data instead of assuming: `Sales_v_Shipper_Status.Shipped` and `Sales_v_PO_Status.Is_Quote`/`Cancelled_Status` all use `1` = true, **not** the `-1` = true convention already confirmed elsewhere in this pipeline (`Part_v_Container.Active`, etc.) — booleans aren't universal across Plex views; would have been a silent bug if reused from memory.
- **`sales_revenue_summary_report` and `sales_order_value_by_status_report` rewritten in place** (same view names, per Emilio's call — no dead views left from the wrong turn):
  - `sales_revenue_summary_report` now rolls up the new `shipping_revenue_report` (shipped-unit revenue, `Sales_v_Shipper_Line.Quantity × Price`) by month and part group, instead of Sales-module order value. Verified: September 2026, $25,500 shipping revenue, 17,000 units.
  - `sales_order_value_by_status_report`'s WIP definition dropped `Job_Status` entirely, per Jennilyn: "we don't need the production status... if the order line isn't a quote, isn't cancelled, and isn't shipped, it's WIP." Now keys off `Sales_v_PO_Status.Is_Quote`/`Cancelled_Status` plus absence of a `Shipped` `Sales_v_Shipper_Line_Release` link. Verified: 32 real WIP lines across 15 orders, $875,475 total (a far richer real picture than the Job_Status version ever produced).
- **4 new views**, all live-verified with real data:
  - `shipping_revenue_report` — shipped-unit revenue detail, sorted by invoice date, part-group breakdown.
  - `shipping_pending_revenue_report` — "Total in Shipping": ready-but-unshipped unit value. Decided 2026-09-01: falls back to the customer price list when `Shipper_Line.Price` is 0 (Plex doesn't finalize price until actual shipment, confirmed on the one real pending shipment) — verified $115,800 ready value on 20,000 ready units, vs. $0 without the fallback. Also carries the "blanket order" flag Jennilyn asked for (`Sales_v_PO_Type.Blanket`, already confirmed live).
  - `shipping_daily_report` — packages/cartons shipped, orders shipped, revenue shipped, per day. Verified: 17 packages, 1 order, $25,500 for 2026-09-01.
  - `inventory_out_of_stock_report` — Vox's exact Out-of-Stock rule (Part_No LIKE `33%`, `Minimum_Inventory_Quantity > 0` — decided a literal 0 doesn't count as "assigned" — `quantity_available < 0`, excluding parts whose `Part_v_Part_Product_Type` indicates Custom). Reuses `part_on_hand_inventory_view.sql`'s already-confirmed on-hand pattern. 0 rows today — `Sales_v_Release_Allocation` (needed for the allocated-quantity half) is genuinely empty on this tenant, not a bug.

### Added
- **9 new `bq_view`s built for the Vox Nutrition Scorecard migration** — `sales_revenue_summary_report`, `sales_order_value_by_status_report` (both `reports/sales_orders.yaml`); `quality_cost_by_category_report` (`reports/quality_nonconformance.yaml`); `quality_fpy_by_area_month_report`, `mfg_job_open_caps_report`, `bottling_job_open_report` (all `reports/work_orders.yaml`); `inventory_valuation_total_report` (`reports/inventory_snapshot.yaml`); `inventory_avg_daily_usage_report` (`reports/inventory_activity.yaml`, converted its `bq_view` from a single mapping to a list to support this — safe against the currently-deployed `main.py`, which already normalizes both forms); `inventory_top_quantity_report` (`reports/part_on_hand_inventory.yaml`). All 6 touched `reports/*.yaml` updated in both prod and `test/` copies, plus 9 new `google_storage_bucket_object` Terraform resources (`terraform fmt -check` clean). **Zero new Plex extractions** — every view reuses already-extracted, already-confirmed-live raw tables or an already-deployed sibling report view (the "thin alias" pattern this repo already uses, e.g. `sales_orders_pending_approval_by_rep_report`). Business-rule calls made 2026-09-01 with Emilio, all matching this repo's existing conventions rather than inventing new ones: MFG_Job/Bottling_Job "open" = inverse of Completed/Cancelled/Hold status flags (same as `labeling_open_work_orders_report`); YTD FPY ships now with DPMO on a documented `Opportunities_Per_Unit = 1` placeholder, Sigma deliberately left uncomputed (a hand-rolled DPMO→Sigma approximation risked being subtly wrong in cGMP-adjacent reporting); Quality_Rework/MatDestr's `$` fields get a category+month rollup (`quality_cost_by_category_report`) rather than a guessed `Problem_Category` string match, since — a real correction to the 2026-09-01 migration-map doc's first pass — `Quality_v_Problem.Cost` already exists and is already exposed by `quality_nonconformance_report`, so this was never actually a "no Plex path" item. **Deployed and verified same day**: `terraform apply` (9 added, 12 changed, 0 destroyed) pushed all 6 configs + 9 SQL files to GCS, then all 6 affected test Cloud Run jobs were manually triggered and every new view queried directly against `PlexTest` — this repo's own house rule, since a clean job exit code has caused false confidence before (see 2026-08-23/24). 8 of 9 views created cleanly on the first pass; `sales_revenue_summary_report` failed with a real bug (below), fixed and re-verified same session.

### Fixed
- **`sales_revenue_summary_report` naming collision.** A subquery selected `DATE_TRUNC(date_approved, MONTH) AS date_approved FROM date_approved` — the bare column reference resolved to the enclosing CTE's own name (`date_approved`) instead of its column of the same name, so BigQuery tried to pass a whole `STRUCT<PO_Key, date_approved>` into `DATE_TRUNC` and rejected the view outright. Fixed by aliasing the inner `FROM date_approved` as `da_inner` and qualifying the reference. Caught by dry-running the view via the BigQuery REST API before redeploying — `bq` itself was unusable in this environment (`python3.12: command not found` from its wrapper script), so verification for this whole session went through direct `bigquery.googleapis.com/bigquery/v2/.../queries` calls instead.
- **`quality_fpy_by_area_month_report` returned 0 rows against real data, same day it was written.** Copied the Daily Reports' `Part_v_Production → Part_v_Job_Op → Part_v_Workcenter` join pattern to reach `Workcenter_Group`, but this view already keyed its `Workcenter_Group` join off `Part_v_Production.Workcenter_Key` directly — the `Job_Op` join was dead weight, and being an `INNER JOIN` it silently dropped every production row once real data landed, because this tenant's real `Job_Op_Key` values in `Part_v_Production` have since aged out of the current `Part_v_Job_Op` extract (Job_Op only reflects current/open operations; the production log is permanent). Fixed by removing the unused join entirely.
- **The same root cause was live in 4 already-deployed reports** (`encap_daily_report`, `blending_daily_report`, `labeling_daily_report`, `packaging_daily_report`) — previously invisible because `Part_v_Production` had zero rows on this tenant since they were built 2026-08-21, so "0 rows, benign" was the correct read at the time. It stopped being benign the moment real production data appeared. These 4 don't have the FPY view's luxury of dropping the join entirely (they still need `Job_Op → Job → Part` for `job_count`/`parts_run`), so each was changed from `JOIN raw_Part_v_Job_Op` to `LEFT JOIN` instead — a production row is never dropped just because its operation has since closed/archived; `job_count`/`parts_run` just go `NULL`-safe for those specific rows. Redeployed and reverified against `PlexTest`: `packaging_daily_report`/`blending_daily_report` now show real rows (Bottling Line 1 and Preweigh 1, both 2026-08-31/09-01, matching `quality_fpy_by_area_month_report`'s own real 100%-FPY read for the same production); `encap_daily_report`/`labeling_daily_report` correctly still show 0 — no real production has been logged against those workcenters yet, a genuine business fact now, not a join bug.

### Verified (real data, not just clean deploys)
- `sales_revenue_summary_report`: September 2026, 9 orders, $695,355 computed revenue.
- `sales_order_value_by_status_report`: 26 real (PO, Job) rows, $695,355 total order value — 0 currently flagged WIP/Ready-to-Ship, because every linked job is still "Scheduled" on this tenant, not Production or Completed.
- `mfg_job_open_caps_report`: 2 real open Encapsulation jobs (Job 83, Job 84), 4,643,140 combined caps pending.
- `quality_fpy_by_area_month_report` (post-fix): Bottling and Pre-Weigh both show real 100% FPY for August 2026 (3,000/3,000 and 429.185/429.185 good/total respectively), 0 rejected, DPMO 0 under the provisional Opportunities_Per_Unit=1 placeholder.
- Everything else (`quality_cost_by_category_report`, `inventory_valuation_total_report`, `inventory_avg_daily_usage_report`, `inventory_top_quantity_report`, `bottling_job_open_report`) creates cleanly but returns 0 rows — confirmed to be genuinely empty upstream extracts (`Quality_v_Problem`, `Part_v_Snapshot`, `Part_v_Cell_Production`/`_Depletion`, `Part_v_Container` all still 0 rows on this tenant), not a query bug.

### Added
- **`score-card-reference/vox_migration_board.html`** (published as a Claude Artifact, shared with Jennilyn) — an interactive tile-by-tile map of the live Looker Studio scorecard against its Plex-native replacement, built from the migration-map doc plus every real number verified above. Click-through detail drawer per tile (old source, new Plex view, verified data, rationale, SQL location), an Andon-style tally strip, and a dedicated section for the 4 genuinely non-Plex items (Goals, CRM pipeline stages, Safety, Cycle Count) with a Sheet/Form-to-BigQuery suggestion for each. Gets redeployed to the same link as more views ship or more real data lands.
- **`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`** — readiness map cross-referencing the Vox Nutrition MTD Scorecard audit docs (dropped into the new `score-card-reference/` folder: a Looker Studio data-source catalog, a chart-by-chart mapping workbook, an interactive navigator, and a field guide) against this repo's actual build state, answering the data scientist's concrete question: what's ready now, and what could feed the scorecard with more work. Scope note: Plex is replacing the Monday.com sync that currently backs 6 of the scorecard's BigQuery sources (`vw_sales`, `vw_pipeline` ×2, `vw_sales_mtd_vs_goal`, `vw_shipping_daily_snapshot`, `shipping_revenue_daily` — confirmed fed by the unrelated `monday-daily-sync-VoxScorecardsLive` scheduler in `docs/EMAIL_SCHEDULE.md`, zero Terraform resources in this repo), so those are in scope as migration targets, not waved off. Biggest finding on re-read of the actual SQL: `sales_orders_report`/`sales_orders_open_report`/`sales_orders_pending_approval_report`/`sales_revenue_by_rep_report` (all deployed on `reports/sales_orders.yaml`) already expose a computed per-order dollar value (`price_total` = price × quantity; `order_total` = `Sales_v_PO.Master_Price`, sparsely populated) — revenue/pipeline-value tiles are largely 🎯 buildable from already-extracted tables, not a NetSuite-only concept as the first pass concluded. Also upgraded the Inventory "Avg. Daily" gap from "no confirmed source" to 🎯 buildable-but-unverified: the already-deployed `inventory_activity_report` (`Part_v_Cell_Production`/`Part_v_Cell_Depletion`) computes monthly depletion per part, a direct lead for a daily-average figure, previously overlooked because earlier notes were about a narrower reorder-point/MSL search. Genuine remaining ❌ no-Plex-path items, unaffected by the Monday retirement: negotiated Goal figures (planning input, not a transaction), CRM Opportunity/Forecast pipeline stages (pre-quote, no Plex object), OSHA Safety tracking, and Rework/Material-Destruction `$` cost fields (no cost column found on any Quality table in any catalog to date).

## 2026-08-26

### Fixed
- **`PlexProd` Daily Reports incident closed.** The 2026-08-24 SAFE_CAST fix (`5897a2c`) had only been verified on `PlexTest` as of 2026-08-25 — `PlexProd` still had no views at all for `encap`/`blending`/`labeling`/`packaging_daily_report` because the prod job hadn't run again. Manually executed `plex-etl-work-orders` in prod and, per this repo's own rule of never trusting a clean exit code, queried all 4 views directly: all exist and are queryable (`COUNT(*) = 0`, still benign — `raw_Part_v_Job`/`raw_Part_v_Job_Op`/`raw_Part_v_Production` confirmed still 0 rows on the real Plex prod host, no real production data has landed yet).

### Added
- **`mfg_job_schedule_inventory_availability_report`** — partial build of the MFG Job Schedule spreadsheet's "Inventory Availability" sub-tab (previously 🔍 Mapped, unbuilt). Covers the 3 columns with a confirmed Plex source (Description, Quantity On Hand, On Order) as a 3rd `bq_view` on the existing `part_on_hand_inventory.yaml` pipeline — no new extraction, just a query joining the already-deployed `part_on_hand_inventory_report` and `purchasing_open_orders_report` views by part number. The tab's other columns (Reorder Point, Avg Daily usage rate, Current QTY Available's allocation-netting logic, % Left, Days on/to Reorder Point) stay deliberately unbuilt — both remaining inputs were checked live against every plausible Plex candidate across two research passes and are either the wrong shape or confirmed empty on this tenant, a data-architect question, not a coding one. Deployed to both `PlexProd`/`PlexTest` via `terraform apply`, verified live. See `docs/reports/mfg_job_schedule_inventory_availability_report.md` and `spreadsheets/mfg_job_schedule_inventory_availability.md`.
- **`mfg_job_schedule_success_metrics_report` / `_fg_testing_pending_report` / `_gate_stats_report`** — builds the remaining 6 MFG Job Schedule sub-tabs (Done YTD, Done 2025, YTD List, 2025 List, FG Testing Pending, YTD Gate Stats), collapsed into 3 views: one continuous job-grain metrics view (no year-archive split — a spreadsheet needs that, a BigQuery view doesn't), a thin filter over it, and a monthly rollup on top. Implements the now-confirmed formulas (Total Days = FG Testing Released − Date Entered, TAT goal ≤84 days, Yield = Caps Made ÷ Capsule Count, Success Rating = gates-passed/3) plus 2 business-rule decisions from Emilio: "Successful" = 100% (all 3 gates, not partial credit), and rework rows are included with a computed `is_rework` flag rather than dropped. 3 new `bq_view`s on the existing `work_orders.yaml` pipeline, deployed via `terraform apply` and verified live against `PlexTest` — this tenant went from 0 real jobs to 25 sometime this week, giving the first real (non-trivial) data to validate against; job 4 already shows a real, non-zero Yield (429/2000 = 21.5%) from actual logged production. Hit and fixed one real bug before shipping: a missing comma between two CTEs caused a `BadRequest: Syntax error: Unexpected keyword METRICS` on the first deploy attempt, caught by querying the view directly rather than trusting the job's exit code. Still open, unconfirmed by this build: whether the Yield formula holds for Blending-only jobs, the Stock-vs-Custom proxy, and whether "latest approved checksheet" really means "FG Testing Released" specifically. See `docs/reports/mfg_job_schedule_success_metrics_report.md` and `spreadsheets/mfg_job_schedule_ytd_list.md`'s "Built 2026-08-26" section.
- **`weekly_production_update_report`** — the last remaining Production tab, previously ⏳ Pending with no sheet content at all until Emilio provided both real tabs (Capacity, Goals) this session. Built the Actual WTD/MTD quantity by department (Encap/Bottling/Labeling/Printing — the first report to cover Printing) plus a pure-date-math "% of month complete," reusing the same non-rejected-`Part_v_Production` pattern as the 4 Daily Reports. Deliberately left unbuilt, per Emilio's calls: Goal/`% of Goal` (no Plex source for business-set targets — decided to keep these manual in the sheet rather than add a reference table), and the entire Capacity tab (no confirmed formula, only Encap has real values on the sheet itself). 4th new `bq_view` on `work_orders.yaml`, deployed via `terraform apply`, verified live against `PlexTest`. See `docs/reports/weekly_production_update_report.md` and `spreadsheets/weekly_production_update.md`.

## 2026-08-25

### Verified
- **Confirmed the 2026-08-24 SAFE_CAST fix on `plex-etl-work-orders-test`**, per this repo's own rule of never trusting a clean exit code — queried all 4 views directly. `PlexTest.encap_daily_report`/`blending_daily_report`/`labeling_daily_report`/`packaging_daily_report` all exist and are queryable (`COUNT(*) = 0`, expected/benign — `raw_Part_v_Production` is still empty). **`PlexProd` is a different story: all 4 views still don't exist at all** (`Not found: Table ... was not found`) — only the test job has been re-run since the fix landed; the prod job (`plex-etl-work-orders`) hasn't run again yet, so prod is still in the broken state the 2026-08-24 "PARTIAL PRODUCTION" email left it in until its next run (scheduled 7:20 PM Mountain, or trigger manually with `gcloud run jobs execute plex-etl-work-orders --region=us-central1 --project=voxdatalake --wait`).

## 2026-08-24

### Fixed
- **Real "PARTIAL PRODUCTION" view-creation failure on all 4 Daily Reports** (`encap`/`blending`/`labeling`/`packaging_daily_report`), caught by the scheduled 7:20 PM Mountain prod run (`plex-etl-work-orders-jgpxv`, 2026-08-25 01:21 UTC). The 4 views' `raw_Part_v_Job_Op -> raw_Part_v_Job` join (`ON jo.Job_Key = j.Job_Key`) and `raw_Part_v_Job -> raw_Part_v_Part` join (`ON j.Part_Key = part.Part_Key`) had no `SAFE_CAST`, from the original 2026-08-21 build. This had been benign as long as every table involved was empty, but `raw_Part_v_Job`/`raw_Part_v_Job_Op` fetched 0 rows again this run — `write_to_bigquery` deliberately leaves an existing empty table's schema untouched on a 0-row fetch (to avoid wiping real data on a transient miss), so those tables never picked up the 2026-08-23 STRING/INT64 root-cause fix, while `raw_Part_v_Part` (populated) autodetects `INT64`. Fixed with `SAFE_CAST(... AS INT64)` on both sides of both joins in all 4 SQL files, pushed via `terraform apply` (0 add / 4 change / 0 destroy). Confirms real prod Plex data (`Part_v_Job`/`Part_v_Job_Op`/`Part_v_Production`) is still 0 rows as of this run — only reference/lookup tables (Workcenter, Job_Status, Employee, etc., 60 rows total) have real data so far.
- **DataDirect ODBC driver license applied for real** — no longer running on the 15-day trial flagged since 2026-07-14. Closed out in `docs/CLICKUP_TEAM_GUIDE.md` §9 and `docs/CODE_REVIEW_2026-07-14.md`'s open items (both had gone stale after the SendGrid item was already resolved 2026-08-21).
- **22 local commits pushed to `origin/main`**, resolving the `git push` permission issue noted in `CLAUDE.md` "Known friction" — repo access was fixed on the GitHub side. Local and remote `main` are now in sync.

## 2026-08-23

### Added
- **`docs/reports/` — business-facing documentation for all 36 deployed reports.** New convention: every report gets a team/ClickUp-facing doc (what it tells the business, where it fits in the company's reporting, how it's built at a high level, open flags/questions) separate from the engineering trail in `reports-list/`/`spreadsheets/`. `docs/reports/REPORT_CATALOG.md` has the template and full index. 34 of the 36 were generated by a parallel multi-agent workflow, each agent independently researching its own report — this caught two real deployment gaps the existing docs had missed (see Fixed below). Going forward, any change to a report's YAML/SQL needs a matching update to its `docs/reports/*.md` doc, same discipline as this file.

### Fixed
- **Code review of the last ~20 commits caught 4 real correctness bugs, fixed and deployed same day:**
  - **Scrap was silently always zero on all 4 Daily Reports** (`encap`/`blending`/`labeling`/`packaging_daily_report_view.sql`) — the scrap check compared Plex's `Rejected` flag to `1`, but this repo's own confirmed convention is that Plex represents boolean true as `-1`. Real rejected units would have vanished from both the actual and scrap totals instead of being counted as scrap. Fixed before any real production data existed to be affected.
  - **`raw_Part_v_Cell_Production` was being written by two independent daily pipelines** (`work_orders` and `inventory_activity`, different schedules) — nothing in `work_orders` read it, and it's already owned by `inventory_activity`. Exactly the WRITE_TRUNCATE race this same YAML file already warns against for another table. Removed from `reports/work_orders.yaml` and its test twin.
  - **The recurring STRING/INT64 view-creation bug is now fixed at its actual root cause, not just patched per-file.** `write_to_bigquery()` used to force every column of an empty raw table to `STRING`; `query_plex()` now reads each column's real type from the ODBC cursor (`extract_schema_catalog.py` already proved this works reliably against this driver) and types the empty table correctly from the start. Verified live: deleted `raw_Purchasing_v_Requisition` on PlexTest and re-ran the job — it came back with real `INTEGER`/`TIMESTAMP`/`FLOAT` types instead of blanket `STRING`. Populated tables are untouched (`autodetect=True` unchanged) — zero behavior change for anything that already worked. Rolled out via `gcloud builds submit --config deploy/cloudbuild.yaml` to all 24 Cloud Run jobs.
  - **A thin alias view's correctness depended on YAML list ordering enforced only by a comment** (`sales_orders_pending_approval_by_rep_view.sql`). The view-creation loop now retries any view that fails on its first pass once, after every other view in that run has been created, so a future reorder self-heals within the same run instead of silently leaving a stale view.
  - Also completed `SAFE_CAST` coverage on the 5 remaining un-cast joins in `sales_order_allocation_view.sql` (only 2 of 7 had been fixed after its earlier production failure), deduplicated a `DATE_DIFF` computed twice in `inventory_risk_analysis_view.sql`, narrowed an unnecessary `SELECT *` before a window function in `sales_orders_rush_open_view.sql`, and fixed inconsistent markdown-cell escaping in `mapping/build_netsuite_saved_searches_catalog.py`.
  - **Found and fixed 2 real bugs in `deploy/cloudbuild.yaml` itself**, surfaced by actually running it for the first time this session: a vestigial unused `_CR_JOB` substitution that Cloud Build rejects at submit time, and the `deploy-all` step's own bash variables (`$job`, `$IMAGE`) colliding with Cloud Build's substitution parser (fixed by escaping to `$$job`/`$$IMAGE`). Also discovered and fixed `_ALL_JOBS` had silently fallen 8 jobs behind the actual Cloud Run job list — those jobs would never have received a new image from this pipeline again. See `CLAUDE.md` for the full gotcha list.
- **Fixed a real STRING/INT64 view-creation failure on all four reports deployed today, caught by their first real runs.** `purchasing_pending_requisitions_report`'s first scheduled prod run sent a real "PARTIAL PRODUCTION" email; `quality_supplier_returns_pending_report`'s first test run sent a "PARTIAL TEST" one. My own initial "clean test run" claims for all four (including Open Quotes/Open RMA's below) were wrong — a Cloud Run job can exit 0 while the view creation inside it still fails silently; direct verification (`bq query ... SELECT COUNT(*)`) showed `sales_quotes_open_report`/`sales_returns_open_report` had never actually been created ("table not found"), not just left stale. Same root cause all four times: the base table (`raw_Purchasing_v_Requisition`, `raw_Quality_v_Supplier_Return`, `raw_Sales_v_Quote`, `raw_Sales_v_Return`) had 0 rows and got autodetected all-`STRING`, while its status/type/customer lookup tables have real data and are properly typed (`INT64`) — joining without a cast breaks view creation outright. Fixed with `SAFE_CAST` on both sides of every join (and every status-exclusion `WHERE` filter) in all four SQL files, pushed via `terraform apply`, re-verified this time by directly querying each BigQuery view rather than trusting the job's exit code. Added a permanent note to `CLAUDE.md` on both the verification gap and the recurring STRING/INT64 pattern.
- **Deployed Approve Vendor Return Authorizations for real.** A systematic sweep (every SQL file and every report YAML checked against Terraform tracking, prompted by the Open Quotes/Open RMA's gap below) found `quality_supplier_returns.yaml`/`quality_supplier_returns_pending_report` also had zero Terraform/GCS footprint — correctly marked "scaffolded" in `reports-list/supply-chain.md` (not falsely claimed deployed like the two below), but still just as unbuilt in practice. Added its own Cloud Run job + scheduler pair (`plex-etl-quality-supplier-returns`/`-test`, 10:40/10:50 PM Mountain) via `terraform apply` — 9 resources added, 0 changed/destroyed. Same sweep confirmed every other report YAML/SQL file in the repo now has Terraform tracking — no more silent gaps.
- **Deployed Open Quotes and Open RMA's for real.** `reports-list/sales.md` and `docs/reports/REPORT_CATALOG.md` both called these "Deployed," but neither `sales_quotes.yaml` nor `sales_returns.yaml` had ever had a Cloud Run job, scheduler, or Terraform resource, and nothing under their names existed in the GCS config bucket — the SQL and business logic were finished and schema-confirmed, but the pipelines themselves were never wired up to run. Added a dedicated Cloud Run job + scheduler pair for each (`plex-etl-sales-quotes`/`-test` at 10:00/10:10 PM Mountain, `plex-etl-sales-returns`/`-test` at 10:20/10:30 PM Mountain) via `terraform apply` — 18 resources added, 0 changed/destroyed. Both jobs' first runs exited cleanly but their views had actually failed to build — see the STRING/INT64 fix above.

## 2026-08-22

### Added
- **`bottling_job_schedule_report`** — Bottling Job Schedule Google Sheet, one row per job operation on a Bottling workcenter (`Workcenter_Group = 'Bottling'`, same confirmed roster as `packaging_daily_report`). 9th `bq_view` on the existing `reports/work_orders.yaml` pipeline — no new extractions or Cloud Run job needed. Built the sheet's confirmed-buildable columns (job/part identity, workcenter, planned qty, lot, operator name, job status) plus its most-promising unconfirmed lead: a Run Time/# Completed reconstruction from `Job_Op` timestamps, exposed with full `TIMESTAMP` precision (every other view in this repo truncates straight to `DATE`, since none of them needed time-of-day). Not attempted: splitting into the sheet's 4 sub-tabs (Liquids/Powders/Gummies/Capsules_Softgels) — no confirmed Plex-side split exists per tab. `terraform apply`: 7 added (including backfilling terraform tracking for 6 already-live SQL files from the 2026-08-21 batch that had the same gap — see Fixed below), 2 changed (`work_orders.yaml` prod+test), 0 destroyed. Verified with a clean `plex-etl-work-orders-test` run.
- **`purchasing_pending_requisitions_report`** — "Vox | Purchasing | Pending Order Requisitions" (NetSuite parity, `customsearch2935`), scaffolded 2026-08-13, deployed today rather than continuing to wait on the real-data recheck. Own Cloud Run job + scheduler pair (`plex-etl-purchasing-pending-requisitions` / `-test`, 9:40 PM / 9:50 PM Mountain) added via `terraform apply` (9 resources: 2 jobs, 4 schedulers, 3 GCS config objects). Business rule: `Requisition_Status.Approved=1 AND Allow_PO=1` and no matching `Purchasing_v_Req_PO_Release` row. Test run (`plex-etl-purchasing-pending-requisitions-test`) completed clean. **Known gap:** the test tenant has zero real Requisition rows, so the `Item_Key` vs `Part_Key` join is unverified against real data — recheck once real requisitions exist.

### Fixed
- **Backfilled missing `terraform` tracking for 6 bq_view SQL files** (`encap_daily_report_view.sql`, `blending_daily_report_view.sql`, `labeling_daily_report_view.sql`, `packaging_daily_report_view.sql`, `sales_orders_rush_open_view.sql`, `sales_order_allocation_view.sql`) — pushed to GCS manually during the 2026-08-21 build (per that day's commit messages) but never given a `google_storage_bucket_object` resource, the same 404-on-first-load gap the 2026-08-19 catch-up batch fixed for a different 12 files. Found while adding the resource for `bottling_job_schedule_view.sql`. No content drift — `terraform plan` showed these 6 as pure adds, not changes, confirming GCS already matched local files.

### Changed
- **Promoted `sales_orders.yaml` and `work_orders.yaml` from test-only to production GCS config.** `terraform plan` (after moving the repo to a new local path) showed `reports/sales_orders.yaml` and `reports/work_orders.yaml` in `gs://voxdatalake-report-configs` were still on pre-2026-08-21 content — every report built that day (4 rebuilt Daily Reports, RUSH Open SOs, Allocation Report, Orders Pending Approval by Sales Rep alias, and the rest of the 2026-08-14/21 NetSuite-parity batch) had only ever been pushed to the `test/` path, not `reports/`. `terraform apply` synced both prod objects in place (plus a content-type metadata fix on the two test objects from an earlier manual `gcloud storage cp`). Verified with a manual run of both `plex-etl-test` and `plex-etl-work-orders-test` — both completed successfully against the new config. These reports go out for real on the next scheduled prod run (7:00 PM / 7:20 PM Mountain) instead of test-only.
- Confirmed the repo move to `c:\F\Parasol\plex-to-big-query` didn't break anything: `docker compose build` succeeds, a live `docker compose up` pulled 73 real rows from `Part_v_Part` against `vox.test.odbc.plex.com` and wrote them locally, and no file in the repo references the old path.

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
- `encap_daily_report`, `blending_daily_report`, `labeling_daily_report`,
  `packaging_daily_report` — the "Actual produced quantity" half of the 4
  Daily Reports Google Sheets, unblocked by a screenshot of Plex's own
  "Daily Shifts" UI report confirming this per-date/per-workcenter rollup
  exists natively. Built on `Part_v_Cell_Production` (new extraction) ×
  `Part_v_Job_Op`/`Part_v_Job`/`Part_v_Part`, filtered by each report's
  `Part_v_Workcenter.Workcenter_Group` (also newly used — already extracted
  but unused until now). Packaging has no matching workcenter group of its
  own (it's a Department code and a Part_Group value instead) — decided to
  map it onto `Workcenter_Group = 'Bottling'`, whose roster matches the
  sheet's line names almost exactly. Deliberately NOT built: Planned
  Production Hours, Start-Up/Stop times, shift checkpoints, and the
  employee Call Outs/OFF attendance roster — no Plex analog identified,
  same treatment as MFG Job Schedule's manual-only columns. Unconfirmed
  against real (non-template) data, same caveat every one of these 4
  reports' docs already flagged.
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
- `sales_order_allocation_report` failed to create at all on first test
  deploy — `Sales_v_Release_Job`'s first-ever extraction returned 0 rows,
  so BigQuery typed all 3 columns STRING, breaking the join against the
  already-INT64 `Sales_v_Release`/`Part_v_Job`. Fixed with `SAFE_CAST` on
  both join conditions.
- `reports/test/sales_orders.yaml` and `reports/test/work_orders.yaml` were
  missing the `Sales_v_Release_Job` extraction and all 6 new bq_views added
  earlier today (Rush, Allocation, 4 Daily Reports) — the prod configs got
  updated but the test mirrors didn't, which would have made `PlexTest`
  silently diverge from `PlexProd`. Caught before deploying test, not after.

### Verified (test deploy, 2026-08-21)
- All 6 new `bq_view`s (`sales_orders_rush_open_report`,
  `sales_order_allocation_report`, `encap_daily_report`,
  `blending_daily_report`, `labeling_daily_report`,
  `packaging_daily_report`) deploy cleanly to `PlexTest` — no errors after
  the `SAFE_CAST` fix above.
- All 6 currently return **0 rows** against real test-tenant data — not a
  code failure, a real data-signal finding: `raw_Sales_v_PO` has 9 real
  orders, none match `RUSH` in `Note` (inconclusive on a sample this
  small); `raw_Sales_v_Release_Job` is empty despite `Sales_v_Release` (8
  rows) and `Part_v_Job` (16 rows) both having real data; and
  `raw_Part_v_Cell_Production` is empty despite 16 real jobs and 38 real
  workcenters existing — the last one raises a real open question (not
  answered here) about whether this tenant uses Plex's Cell Production
  tracking mode at all. See `reports-list/sales.md`,
  `reports-list/production.md`, and `docs/NETSUITE_PARITY_OPEN_ITEMS.md`
  for the full per-report detail.

### Fixed (correction, same day)
- The "Cell Production tracking mode" open question above turned out to be
  the wrong question. Live Plex screenshots (Job Manager, Job Detail, Job
  Routing, Job Production report) showed the real cause of the 0-row
  result was benign: all 16 real jobs on this tenant were created that
  same morning with 0 actual hours logged anywhere — nothing had run yet,
  full stop. But the investigation also caught a real correction: Plex's
  own "Job Production" UI report (confirmed columns Job No/Part No/Rev/Op
  No/Tracking No/Last Operation Completed/Workcenter/**Employee**/Record
  Date/**Shift**/Quantity) matches `Part_v_Production` field-for-field, not
  `Part_v_Cell_Production` (no Employee/Shift/Rejected columns at all).
  Rebuilt all 4 Daily Report views on `Part_v_Production` (new extraction,
  `Part_v_Cell_Production` kept extracted but unused going forward) —
  redeployed to `PlexTest`, all 4 create cleanly, still 0 rows for the
  now-understood benign reason. This also resolves 2 of the 3 "no Plex
  analog" gaps flagged at build time: `employee_count`/`employees`
  (`Record_By` → `Personnel_v_Employee`, same INFERRED-join pattern already
  used for `Job_Op.Started_By`/`Completed_By`) and `scrap_qty` (a genuine
  `Rejected` flag) are now exposed on all 4 reports.

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
