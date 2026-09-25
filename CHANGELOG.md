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

## 2026-09-25 (dev-label-design) - Deploying from a second machine

### Added
- **macOS checksums in `terraform/.terraform.lock.hcl`** (`darwin_arm64`,
  2 lines). The provider versions are unchanged. Without them a Mac's first
  `terraform init` dirties the tree, and the deploy guard refuses.
- **CONTRIBUTING.md / README: how to deploy from another machine.** Restore
  tfvars from `gs://voxdatalake-terraform-state/plex-to-big-query/terraform.tfvars.backup`,
  check it isn't stale, and set up ADC and a `python` on `PATH` for the
  guard. Done for the first time today: the backup (2026-09-22) matched
  every value checked in the live state.

## 2026-09-25 (dev-label-design) - Plex Part URL and PO URL on the Monday push

### Added
- **Two Monday link columns from the Label Design push:** "Plex Part URL"
  (`/Engineering/Part/ViewForm?…PartKey=&PartNo=&Revision=`) and "PO URL"
  (`/SalesAndCRM/OrderEntry/ViewOrderForm?POKey=`).
  - `label_design_view.sql` now outputs `po_key`, `part_key`, `part_no`,
    `part_revision`. The last two come from a new `raw_Part_v_Part` join.
  - `Part_v_Part` is now extracted by `label_design` (prod + test configs,
    13 extractions each). That keeps parts created the same morning
    linkable, rather than waiting for the overnight `sales_orders` refresh.
  - `push.py` builds the URLs, with the host taken from `PLEX_WEB_HOST`
    (set to `vox.test.on.plex.com` on the test job; defaults to
    `vox.on.plex.com` for `PlexProd` — unverified).
  - The columns are matched by title and type `link`. They must be added
    to "Plex Import" (18432111755) by hand; until then the push logs them
    as missing and carries on.

## 2026-09-25 (dev) - One open-items list; deploy.sh cleans up after itself

### Added
- **`docs/OPEN_ITEMS.md`:** every open item across Deploy, Scorecard and
  Label Design, with owner and next step. Linked from the README and
  CLAUDE.md. Items are deleted when they close; the history stays in this
  file.

### Fixed
- **`scripts/deploy.sh` left `deploy.tfplan` / `deploy.plan.json` behind**
  when it was stopped at the confirmation prompt. The tree then stayed dirty,
  so the deploy guard refused every later plan (seen 2026-09-25, when a run
  was declined).
  - A `trap … EXIT` now removes both however the script ends.
  - Both files are gitignored.
  - Nothing had been applied by that run: no `deploy/` tag exists.

### Found - what the next deploy proposes
PR #3 brought `2eff172` into `main`, so a plan now shows **3 to add, 3 to
change**:
- **added:** the `monday-api-key` secret, plus the
  `plex-etl-label-design-push-test` job and scheduler;
- **changed:** `label_design_view.sql` (the BDM sales-rep fields), plus two
  comment-only SQL files.

The scheduled push job fails until its secret version and a new image
exist. That decision is `docs/OPEN_ITEMS.md` D1 / L1.

## 2026-09-25 (dev) - Terraform lock file records the deploy guard's provider

`terraform/.terraform.lock.hcl` gains `hashicorp/external` 2.4.2, the
provider behind `data "external" "deploy_guard"`. `hashicorp/google` is
unchanged at 5.45.2.

The file had been tracked since the first apply, but `.gitignore` also
listed it. That made it look disposable, so any `terraform init` left the
primary folder dirty and the deploy guard refused. It is now committed on
purpose, and the misleading ignore line is replaced with a note.

## 2026-09-25 (docs) - Documentation reviewed end to end for the new workflow

A read-only audit of every doc in the repo (verdicts per file) drove the
fixes.

### Changed
- **The deploy docs no longer teach the mechanism behind the 2026-09-22
  rollback.**
  - **What they used to say:** CHEATSHEET, OPERATIONS and a comment in
    `terraform/main.tf` told people to `gcloud storage cp` YAML/SQL straight
    into the prod GCS paths "with no deployment".
  - **What they say now:** iterate on YAML in `test/` only. SQL objects are
    shared by prod and test, so iterate on SQL with dry-run queries or the
    ScorecardSandbox. Everything lands through a dev branch → `main` →
    `./scripts/deploy.sh`.
  - The `main.tf` comment also wrongly claimed Terraform manages only the
    initial copy of each object.
- **Every engineering guide:**
  - Counts corrected: 13 pipelines / 26 jobs / 52 schedulers / 68 views, not
    8/16 or 12/24.
  - Legacy `plex-etl` / `plex-daily-sync` names replaced.
  - Bare `terraform apply` replaced by `deploy.sh`, except in genuine
    bootstrap and recovery steps, which now explain the guard.
  - `-auto-approve` advice removed.
  - `SHORT_SHA` stated as manual for local builds.
  - EMAIL_SCHEDULE rebuilt from `main.tf`, including Label Design.
  - Incremental sync documented as not implemented (no `WRITE_APPEND` /
    `get_last_sync` exists).
  - Each reviewed doc carries "Last reviewed: 2026-09-25".
- **`terraform/terraform.tfvars.example`** still set the pre-2026-09-04 job
  and scheduler names. Cloud Run names are immutable, so a fresh setup copied
  from it would have **destroyed and recreated** the Sales Orders jobs under
  the old names. It now matches `variables.tf`; the live `terraform.tfvars`
  was already correct.
- **Archived to `docs/archive/`** (history, with banners):
  `CODE_REVIEW_2026-07-14.md`, `APPLY_DRIVER_LICENSE.md` (licensed
  2026-08-24) and `NETSUITE_PARITY_OPEN_ITEMS.md`. Links in 21 files are
  repointed; none are broken. Two of those links sit in comments in
  `sales_orders_pending_approval_by_rep_view.sql` and
  `sales_orders_rush_open_view.sql`, so the next deploy re-uploads them with
  comment-only changes.
- CHEATSHEET, README, CONTRIBUTING and the report docs were committed
  separately today (see `git log`).

### Found - the 9:45 PM retry has never produced a run
`job_run_log` holds **zero** `run_mode = 'retry'` rows since logging began
(2026-07-21). Over the same period there were 1 failed and 9 partial prod
runs, and 22 failed and 30 partial test runs. So either:
- the retry schedulers never fire; or
- the retry path exits without logging; or
- retries always find "already ran today".

Separately, the retry's "today" is the UTC date while the schedules are
Mountain. That could make it misjudge jobs that run after 9:50 PM, but the
empty log shows it is not re-running them.

**Not diagnosed yet:** checking the retry schedulers and executions needs
`gcloud`, which was behind the reauthentication wall. It's a real gap: the
failure-retry safety net described in OPERATIONS may not be doing anything.
## 2026-09-25 (label design) - Run the Label Design sync on demand from a web app

### Added - `deploy/label_design_trigger/` (Apps Script web app)
A one-button page that starts the Label Design Cloud Run job, so the team can
refresh `label_design_report` without waiting for 09:30 / 13:30. It also
shows the last five executions with log links, and who started what.

- **Test job first.** `JOB_NAME=plex-etl-label-design-test`. Promoting to
  prod is one Script Property change, and the page badge turns red.
- **Runs as the deployer, gated by an `ALLOWED_EMAILS` allowlist.** Nobody
  else needs GCP permissions; everyone else gets view-only.
- **It refuses** while an execution is running, and within
  `COOLDOWN_MINUTES` (default 10) of the last start. A script lock
  serialises simultaneous clicks.
- **Every start, refusal and error** is kept in `RUN_LOG` and shown on the
  page.
- **Checked against the live Cloud Run v2 API before commit:**
  - The executions list returns `startTime` / `completionTime` /
    `succeededCount`, as read.
  - `POST …/jobs/plex-etl-label-design-test:run` returns the new execution
    in `metadata.name` (`plex-etl-label-design-test-w5kvn`, an ordinary test
    sync).
- **It only starts the existing job.** Nothing Terraform-managed changes.
  Setup and promotion steps are in its README.

First feature built through the new flow: made in `ptbq-label-design` on
`dev-label-design`, committed past the hooks, and merged to `main` by PR.

## 2026-09-25 (dev) - Locks: a folder per project, commit/push hooks, a deploy guard inside Terraform

Three things went wrong on 2026-09-24:
- two sessions shared one working tree;
- a whole day of Label Design work sat uncommitted on `dev-scorecard`;
- an apply from `dev-scorecard` had already rolled back a Label Design fix
  in prod (2026-09-22) without anyone noticing for two days.

The 2026-09-17 setup relied on people remembering a preflight script. These
locks don't.

### Added
- **A git worktree per project.**
  - The folders are `ptbq-scorecard`, `ptbq-sandbox`, `ptbq-label-design`
    and `ptbq-dev`, next to the primary `plex-to-big-query` folder, which
    stays on `main`.
  - Git refuses to check one branch out twice.
  - Five `*.code-workspace` files open these folders, one per project plus
    main (deploy) and dev (shared), each with a coloured title bar.
  - Replaces the two workspace files that both opened `"."`, which is how
    two sessions ended up in one tree.
- **`.githooks/`** (pre-commit, pre-push, logic in `hooks.py`), installed by
  `scripts/install_hooks.sh` via `core.hooksPath` (covers every worktree).
  Each block has a named, printed, one-command override. They block:
  - a commit in a folder whose branch was switched;
  - non-merge commits on `main`;
  - another project's files on a project branch, or one commit mixing
    projects;
  - `reports/` or `terraform/` changes without `CHANGELOG.md`;
  - prod/test YAML `plex_view:` counts that differ (the 2026-09-09
    incident);
  - pushing a dev branch into `main`, or a non-fast-forward push to it.

  Which file belongs to which project is defined once, in `hooks.py`.
  All blocks and the pass case were exercised against staged dummy changes
  in each folder before commit.
- **Deploy guard inside Terraform:** `data "external" "deploy_guard"` runs
  `scripts/tf_guard.py` on every plan and apply.
  - **It refuses** unless the run is in the primary folder, on `main`, with a
    clean tree, and `HEAD == origin/main`. It cannot be forgotten.
  - `TF_GUARD_OVERRIDE="why"` allows a read-only plan elsewhere.
  - Needs the `hashicorp/external` provider (`terraform init -upgrade` once).
  - Tested: it refuses from `ptbq-dev` on all three counts, passes from
    `main`, and passes with the override.
- **`scripts/deploy.sh`**, the one way to apply:
  1. preflight, then fetch, and require equality with `origin/main`;
  2. `plan -out`;
  3. `scripts/plan_review.py`, which downloads every changed GCS object and
     separates real content changes from line-ending re-uploads, listed by
     project, and flags destroys;
  4. type the change count to confirm;
  5. apply exactly that plan;
  6. tag `deploy/<UTC time>` and push the tag.
- **`.gitattributes`:** LF for `reports/**`, `deploy/**`, `terraform/*.tf`
  and scripts. Checkouts become byte-identical to commits, so plans stop
  listing phantom changes (2026-09-24: 8 of 30). GCS objects uploaded as
  CRLF re-upload once, then settle.

### Changed
- `CONTRIBUTING.md`: the branch section is rewritten as folders, locks and
  the change → main → deploy → re-sync flow.
- `README.md` and `docs/OPERATIONS.md` Step 5 point at `deploy.sh`.
- `CLAUDE.md` gains a folders/locks section for sessions.

## 2026-09-25 (label design) - Restored the part-attribute pivot fix that a scorecard apply rolled back

### Fixed - `label_design_view.sql` in prod is the shipped version again
- **What was lost:** `80c6431` added `NULLIF(TRIM(pa.Value), '')` on every
  attribute, plus five new attribute columns. It was applied 2026-09-22 and
  overwritten about an hour later by an apply from `dev-scorecard` (GCS
  update 2026-09-23 00:18 UTC; see the 2026-09-24 (deploy) entry).
- **Merge:** `dev-label-design` up to `588fd2b` into `main` as `7563821`. The
  view is byte-identical to `588fd2b` and has all 10 `NULLIF` branches.
- **Dry-run before the apply**, against PlexTest (6 rows, `part_allergen`
  NULL rather than `''`) and PlexProd (0 rows):
  - It compiles on both.
  - Row counts match the live view and no column is dropped.
  - It adds `part_bottle_material`, `part_california_pdp`,
    `part_prop_65_requirement`, `part_trademark` and
    `part_material_classification`.
- **Plan:** 0 add / 1 change / 0 destroy, `label_design_view_sql` only.
- **Not included:** `2eff172`. Its push-job terraform needs the Monday API
  key secret version and a rebuilt image first.

## 2026-09-25 (deploy) - Scorecard view fixes applied and verified

### Deployed - `terraform apply` from `main` (`65eefcb`), 2026-09-25 01:10 UTC
The plan was 0 add / 30 change / 0 destroy: 22 content changes and 8
line-ending-only. A re-plan afterwards shows **No changes**.

**Verified on real PlexTest data after the test runs**, one view at a time:
all six test jobs succeeded and the logs show no failed view.
- **Sales rep:** 16 of 21 sale lines now resolve a rep (9 from the order,
  7 from the customer). All 21 were "(no rep assigned)" before.
- **Part group:** `Part_v_Part_Group` loaded 13 rows. The `sales_orders_test`
  job loaded 27 extractions, which matches `grep -c plex_view`. All 21 sale
  lines read "Capsule", where every one was NULL before.
- **Scrap:** the real rejected records (1,000 units) now count as scrap and
  rejects in production monthly, FPY and the packaging daily report. They
  read 0 before.
- **Open caps:** 2 jobs and 1,542,000 caps, up from 200,000. The job on
  Schedule Encapsulation now counts.
- **Disposition cost:** blanks split 26 open / 1 closed with the disposition
  missing / 1 closed with no material. **TAT** has work-day columns (2
  closed NCs). **Average daily usage:** the month in progress uses its 25
  days elapsed.
- **Returning 0, and correctly so:**
  - Deposit Review: no PlexTest order is in either Deposit Review status.
  - Inventory value: $0, because none of the 5 costed parts is on hand.
  - Deviation → NC: the only link row belongs to a deviation Plex has since
    deleted.

**Prod** switches as each pipeline next runs:
- Work Orders already did, at 01:20 UTC: the PlexProd views were recreated
  at 01:22 from the new SQL.
- Quality and Inventory run from 02:20 UTC the same night.
- Sales Orders ran at 01:00, just before the apply, so its fixes, and the
  new extraction, land at the next 01:00 UTC run.

Still not fixed in prod: the Label Design view rollback (2026-09-24
(deploy) entry). It needs `dev-label-design` merged to `main`.

## 2026-09-24 (deploy) - dev-sandbox merged to main; a Label Design rollback found in prod

### Found - prod has been running the pre-fix Label Design view since 2026-09-23 00:18 UTC
- **What was supposed to be live:** `80c6431` shipped the part-attribute
  pivot fix (`NULLIF(TRIM(pa.Value), '')` on all ten attributes) to prod on
  2026-09-22 from `dev-label-design`.
- **What happened:** an apply from `dev-scorecard` that evening, a branch
  that never had the commit, rewrote `gs://…/sql/label_design_view.sql` with
  the old view.
- **Evidence:** the object's update time is 2026-09-23 00:18 UTC. It matches
  `dev-scorecard`'s copy byte for byte, and has 0 of the fix's 10 `NULLIF`
  branches.
- **Why nothing caught it:** the view still builds; it just emits `''`
  instead of NULL again.
- **NOT fixed by this deploy.** Merging the Label Design commits into `main`
  is a decision for that workstream. Until it happens, every apply from
  `main` keeps the old view. `2eff172` (the push job) must not go with it
  until its secret version and image exist.

### Deploy - `main` = `dev-sandbox` (merge `3de2121`)
`terraform plan` from `main`: 0 to add, 30 to change, 0 to destroy.
- **22 are real content changes:** the view fixes dated 2026-09-24 above,
  plus both `sales_orders` configs, which gain the `Part_v_Part_Group`
  extraction.
- **8 are line-ending only:** the Label Design, Part On-Hand and Quality NC
  configs, and two views. GCS holds a mix of LF and CRLF uploads. Each
  object was verified by downloading it and comparing with `\r\n`
  normalised; the check is a short Python loop over `terraform plan`'s
  object list, comparing `gcloud storage cp` output with each resource's
  `source`.

### Docs
Status notes added to `reports-list/{production,sales,quality}.md` and the
four `spreadsheets/*_daily_report.md` trackers. CLAUDE.md "Known friction"
now records the cross-branch rollback and the line-ending plan noise.

## 2026-09-24 (scorecard) - Fixed: inventory value, part groups, daily usage, cycle count, open caps

### Fixed - found by the scorecard sandbox (not deployed; reaches prod on the next apply after merge)
- **Inventory value read about $77 for the whole building.**
  - **Before:** `inventory_valuation_summary_view.sql` summed per-unit
    standard costs with no quantity, added every operation's cost for a part,
    and took the cost model from the snapshot (NULL on real rows).
  - **Now:** value = on-hand quantity (`part_on_hand_inventory_report`) ×
    unit cost. The unit cost is the part's latest cost rows at its
    highest-costed operation (costs are cumulative through the routing),
    summed across the cost sub-types. The cost model comes from the history
    rows. Plex's snapshot pointer table is used when populated, otherwise the
    cost history on or before the snapshot date.
  - **In the sandbox:** $76.65 → $2,760,901.76, matching an independent
    on-hand × latest-cost query to the cent.
  - **Limitation:** `Part_v_Snapshot` has no quantity, so only the current
    snapshot is valued. There is no month-end trend yet.
- **Revenue by part group was always one "(no group)" bar.**
  - **Before:** four views joined `Part_Group_Key` to
    `Part_v_Part_Product_Group`, which is empty in test and prod.
  - **Now:** the real lookup, `Part_v_Part_Group` (13 groups: Capsule,
    Label, Powder, …), is extracted in both `sales_orders` YAMLs (27
    `plex_view:` each). `shipping_revenue_report`, `sales_mtd_by_status_change`,
    `sales_orders` and `sales_orders_open` join it.
  - Every group key on the parts resolves. Sandbox August revenue: Capsule
    $3.8M, Label $0.45M, Powder $0.37M.
  - **Group names appear in PlexTest/PlexProd only after the next apply +
    Sales Orders run.**
- **Average daily usage understated the month in progress.**
  - **Before:** it divided by all the month's days.
  - **Now:** it divides by days elapsed, and adds `days_in_period`,
    `is_month_in_progress` and `unit`.
- **Cycle count accuracy was weighted per count.**
  - **Now:** each location is judged once a month, on its latest count;
    `locations_counted` is the denominator; `recounted_locations` is added.
- **Open caps missed "Schedule Encapsulation".**
  - **Before:** it filtered by work-centre name. A real open job (1.34M caps)
    sits on that work centre.
  - **Now:** it filters by `Workcenter_Group = 'Encapsulating'`, like Open
    Bottles.

Report docs updated for each view. `docs/reports/part_cycle_count_report.md`
has never existed, which is a gap against the report-doc convention.

### Changed - `scripts/scorecard_sandbox/build.py`
A table first extracted after `build.SNAPSHOT` (`raw_Part_v_Part_Group`) has
no time-travel version, so it is now copied as it is now, and the build says
so. The sandbox's copy holds the 13 real rows pulled from the Plex test host.

## 2026-09-24 (scorecard) - Fixed: deviations' linked NC, TAT in work days, disposition-cost flags

### Fixed - found by the scorecard sandbox (not deployed; reaches prod on the next apply after merge)
- **`quality_deviation_view.sql`: the linked NC never showed.**
  - **Before:** `problem_links` joined the classic `Quality_v_Problem`, which
    is permanently empty; this join was missed when the Quality reports
    moved to `Quality_v_Problem_2` on 2026-09-22.
  - **Now:** it reads `Problem_2`. Verified: the real link row (problem key
    117294) is Problem_2's NC #21. Sandbox: 49 of 151 deviations now show
    their NC, up from 0.
  - **Added** `deviation_month`, by add date, so the tile needn't choose
    between add date and effective date.
- **`quality_turnaround_time_view.sql`: TAT is counted in work days.**
  - **Before:** turnaround was `DATE_DIFF(DAY)` (calendar days), judged
    against Performance/Bonus standards that are work days.
  - **Now:** it adds `turnaround_work_days` (Mon–Fri) for both clocks, and
    the met/missed flags use it. The calendar columns are unchanged.
  - There is no holiday table, so holidays count as work days.
- **`quality_disposition_cost_view.sql`:**
  - **`records_missing_cost`** only counted NULL, but an unfilled Plex Cost
    is 0.00 on every real record. It now counts NULL or 0 on Scrap/Rework.
  - **"(not yet dispositioned)"** was open and closed-without-material
    records together. It is now split into open / closed with no material /
    closed with the disposition missing (sandbox: 91 became 32 / 58 / 1).

Report docs updated for all three views.

## 2026-09-24 (scorecard) - Fixed: sales rep, scrap flag and Deposit Review in nine views

### Fixed - found by the scorecard sandbox, verified against real Plex rows
Each fix was proven in `ScorecardSandbox`, then compiled and run against real
PlexTest data. None of them is deployed yet: they reach prod on the next
`terraform apply` after `dev-sandbox` is merged.

- **Sales rep.** Affects `sales_mtd_by_status_change_view.sql`,
  `pipeline_plex_value_view.sql` and
  `sales_orders_pending_accounting_approval_view.sql`.
  - **Before:** they read the rep from `Sales_v_Order_Salesperson`, which Vox
    barely uses (one row in all of test, none in prod), so every sale read
    "(no rep assigned)".
  - **Now:** the rep resolves order `Inside_Sales` → customer `Assigned_To` →
    `Order_Salesperson`, the same as the Label Design view's `bdm`. The sales
    view adds `sales_rep_source`.
  - **In the sandbox:** 2,704 of 2,720 sale lines resolve a rep (2,559 from
    the order, 145 from the customer).
- **Scrap is `Rejected != 0`.** Affects the production monthly, FPY and encap,
  packaging, labeling and blending daily views.
  - **Before:** the views tested `= -1`, a change made 2026-08-23 on an
    assumed convention. The only real rejected record has `Rejected = 1`, so
    scrap, rejected quantity and DPMO read 0 from then until now. FPY was
    unaffected.
  - **Now:** `!= 0`, which holds for either value.
  - `docs/CHEATSHEET.md`'s boolean table no longer lists any column as
    confirmed `-1 = true`.
- **Deposit Review.** Affects
  `sales_orders_pending_accounting_approval_view.sql`.
  - **Before:** it matched `= 'DEPOSIT REVIEW'`, but Plex now has two
    "Deposit Review (…)" statuses (2587, 2656), so the tile was empty.
  - **Now:** `LIKE 'DEPOSIT REVIEW%'`.

Report docs updated for all nine views. The sandbox's `proposed_sql/`
overrides for these fixes are deleted now that the fixes live in
`reports/sql/`.

## 2026-09-24 (scorecard) - What the sandbox found: six view bugs and a stale-data trap

### Found - `docs/SCORECARD_SANDBOX_FINDINGS.md`
The sandbox built above found these problems. Each one was checked against
the real Plex record before it was written down. Tile-by-tile status and the
manual-input list for Jennilyn are in the doc.

1. **Every sale reads "(no rep assigned)".** The sales, pipeline and
   deposit-review views take the rep from `Sales_v_Order_Salesperson`: one
   row in all of test, none in prod. Vox records it on the order
   (`Inside_Sales`) and the customer (`Assigned_To`), as the Label Design view
   found today.
2. **Scrap, rejected qty and DPMO are always 0.** The views count
   `Rejected = -1` (an assumed convention, 2026-08-23); the only real rejected
   record has `Rejected = 1`. FPY is unaffected.
3. **Orders pending accounting approval is empty.** It matches
   `= 'DEPOSIT REVIEW'`, and Plex now has two "Deposit Review (…)" statuses.
4. **Inventory value reads about $77.** The valuation view sums per-unit
   standard costs with no quantity.
5. **Deviations never show their linked NC.** The view joins the classic
   Problem table, which is always empty.
6. **Revenue by part group is a single "(no group)" bar.** The group lookup
   table is empty in test and prod, though parts carry a group key.

Also:
- TAT counts calendar days against work-day standards.
- Average daily usage understates the current month.
- The ETL keeps yesterday's rows whenever Plex returns 0, so a tile whose
  data genuinely empties shows stale figures silently.

### Added - `scripts/scorecard_sandbox/proposed_sql/` (sandbox only, NOT deployed)
Fixes for 1–3, used by the sandbox build only, which prints a ⚠ line for
each so nobody mistakes them for production behaviour:
- rep resolution: order, then customer, then salesperson;
- `LIKE 'DEPOSIT REVIEW%'`;
- scrap counted as `Rejected != 0`.

Editing `reports/sql/` was deliberately left for Emilio's decision, since it
deploys to prod on the next `terraform apply`. 4–6 have no fix written yet.

## 2026-09-24 (scorecard) - Scorecard sandbox: a full simulated year to design Looker Studio against

### Added - `scripts/scorecard_sandbox/` and dataset `voxdatalake.ScorecardSandbox`
PlexProd is empty until cutover, and PlexTest had one thin month and is
overwritten nightly, so no scorecard tile could be designed against real
shapes. `python scripts/scorecard_sandbox/build.py` (about 7.5 min) builds a
dataset the ETL never writes:
- all 35 tile views, created from the same `reports/sql/` files;
- the 53 base tables under them;
- a coherent history from 1 Jan 2026 to the build day.

All 35 views plus `safety_incidents` return data, most spanning 9–11 months.
**Not real business data:** document numbers are `SBX`-prefixed.

The rule it keeps (Emilio's): no random rows.
- Every synthetic Plex row is a clone of a real PlexTest row, going into the
  same `raw_*` table the ETL writes.
- Manual tiles read the manual-data app's own tables.
- Scale comes from the live scorecard (`scale.py`, cited):
  - sales $3.7–5.3M a month against real rep goals;
  - WIP $5.6M; In Shipping $0.95M;
  - production against the live goals (Encap 100M, Bottling 1.5M,
    Labeling 700K);
  - FPY 90.6% / 99.88% / 99.2%;
  - open caps 219.7M; out of stock 6; cycle count accuracy 98.7%.
- Costs exist only in the sandbox, derived from real prices and cost ratios.

Built from PlexTest **as of 2026-09-23 12:00 UTC via time travel**
(`build.SNAPSHOT`). Live PlexTest joined nothing: 0 of 2,119 customer part
prices matched a customer part after the tenant was cut back from 182
customers to 24. `snapshot_check.py` scores any instant by the joins the
views depend on.

Five generators, each owning disjoint tables:
- `manual`: goals, safety;
- `sales`: orders through invoices;
- `production`: jobs, ops, production log;
- `quality`: NCs, deviations;
- `inventory`: containers, movements, cycle counts, standard costs.

Full design in `scripts/scorecard_sandbox/README.md`, including the few
tables with no real row to clone and how each was handled. Supersedes
`scripts/scorecard_test_data.py` for design work (the build strips that
injector's rows).

## 2026-09-24 (label design) - Sales Rep from Plex's BDM fields; part number to "Item"

### Changed - `label_design_view.sql`: three new columns, `bdm` feeds Monday
All of Ashley's test orders arrived with a blank Sales Rep. The view read it
from `Sales_v_Order_Salesperson`, which Plex barely uses (**one row in all of
test**, and with `Sort_Order = 0`, which the view's `= 1` filter skips as
well). The rep actually sits in Plex's "BDM" field group:
- `sales_rep_inside` ← `Sales_v_PO.Inside_Sales` ("Inside Salesperson"),
  set on every order she entered from SO 4 on.
- `customer_account_rep` ← `Common_v_Customer.Assigned_To` ("Assigned To"),
  set on 16 of 24 test customers, but not Meo Nutrition or Nature's Therapeia.
- `bdm` = COALESCE(order, customer, `sales_rep_primary`).

Both source columns come from tables the pipeline already extracts, so no
new extraction is needed. All 6 of her rows now resolve (Janet Pacheco,
Landen Epperson, Ashley Quintana). **The view was recreated directly in
PlexTest for testing. Prod and the GCS copy update on `terraform apply`**
(`label_design_view_sql`). Until then, a scheduled ETL run puts the old SQL
back.

### Changed - push: Sales Rep ← `bdm`; new mapping Item ← `customer_part_no`
"Item" is the text column next to Design File, where Design & QA keeps the
product. It is not the item name column, which there holds the team-assigned
label code (`CL3822`, `s6191`). The 13 items already on `18432111755` were
backfilled in place (Item on all 13; Sales Rep on Ashley's 6). A follow-up
dry run showed 0 new rows.

## 2026-09-24 (label design) - Plex → Monday push job, with tracked test data

### Added - `label_design_service/push.py` + `monday.py`
The standalone push decided on 2026-09-15, replacing the Sheet + Apps Script
hop. It reads `label_design_report` and creates one Monday item per new order
+ part in a "New from Plex" group (created if missing). Items are named after
the label SKU and fill Customer Name, Date, Description, Sales Order, Memo,
Reason Code, Email, Phone Number, Sales Rep (status) and LCR. Columns are
found by **title and type at runtime**, not id, so the same code works on any
board shaped like Design & QA.
- **Dedupe:** LCR = first 12 hex chars of SHA-256(`dedupe_key`), written
  inside `create_item`, so a run that crashes right after creating an item
  still leaves the mark behind. The audit table is checked too.
- **Audit:** every attempt goes into `<dataset>.label_design_push_log` (created
  on first run, written with DML so test rows are deletable at once).
- **Alarm:** more than `MAX_NEW_ITEMS` (60) new rows means the keys broke.
  Nothing is pushed and the job exits 2.
- Reason Codes are written by **label text** (`REASON_CODE_LABELS`, added to
  `reason_code.py`), not index, since index numbers are per-board.

### Added - `scripts/label_design_test_data.py` (`--inject` / `--status` / `--delete`)
Plex test has no release in Label Design, so the view is empty. This injects 7
marked lines (6 orders; one per Reason Code, one note with no code, one order
with two parts) into the PlexTest raw tables. The marks: keys in
[991000000, 992000000), clear of the scorecard injector's 990000000 range, and
order numbers starting `ZZTEST-LD-`. `--delete` removes the BigQuery rows, the
Monday items (found by Sales Order text) and their audit rows. PlexTest only.

### Verified
Injected 7 lines → all 7 visible in `PlexTest.label_design_report` → push
created 7 items on `18432111755`, read back column by column, with no new
status labels created → **an immediate second run created 0** (7 already on
the board). The test items are still on the board for Ashley.

**Then on Ashley's own Plex-test orders**, entered 10:12–11:06 MT after the
9:40 ETL: re-ran `plex-etl-label-design-test` and the view returned 6 rows
(SO 9 ×2, SO 11 ×3, SO 13). The push created 6 items with the right Reason
Code from each bare-digit note. Worth raising with her:
- SO 11 has part 93005-04VOXNU-0 on 3 lines with notes 2/4/1. The view
  collapses order + part to one row (`release_count = 3`), so only code 2
  reached Monday.
- SO 6 and SO 14 are Label Design releases on **Quote** orders, so the view
  leaves them out.
- None of her orders has a sales rep, and no test part has a description.
- She also added a new release status, **Blanket** (3639), which the view
  ignores.

### Added - Terraform (plan: 3 to add, 0 to change) — NOT YET APPLIED
`google_secret_manager_secret.monday_api_key`, Cloud Run job
`plex-etl-label-design-push-test` (same image, `args = python -m
label_design_service.push`, PlexTest → 18432111755, `max_retries = 0`) and
scheduler `plex-label-design-push-sync-test` at 10:10 / 14:10, 30 min after
the test ETL. No prod job yet: prod has no Label Design releases before the
19 Oct cutover, and the prod target board isn't decided.
`Dockerfile` now copies `label_design_service/`; the job was added to
`_ALL_JOBS` in `deploy/cloudbuild.yaml`.

### Found - Design & QA's "Waiting on Customer" is Monday's default slot
Design Status uses index 5 for "Waiting on Customer". Index 5 is where Monday
puts any new item with no status, so every item created without one (the
push, CSV imports, hand-made items) starts as "Waiting on Customer". This is
a board setting, not something the push writes.

## 2026-09-24 (label design) - Design & QA history copied onto the new "Plex Import" board for Ashley

### Added - `scripts/copy_monday_board.py`
Copies a Monday board's columns, groups **and items** onto another board
(`replicate_board_columns.py` copies structure only). `--wipe-target` clears
the target first. Status labels keep their source index numbers so colours
match; labels beyond Monday's ~20-per-`create_column` cap are added as items
are written (`create_labels_if_missing`). Formula columns are recreated with
their `{column_id}` references remapped. If one value makes Monday reject an
item, the item is created bare and its values are set one column at a time,
so only the bad value is lost.

### Changed - board `18432111755` ("Plex Import", workspace "blank landing page")
Wiped (5 placeholder items, 3 default columns, 2 default groups), then filled
from Design & QA (`18395121955`): 59 columns, 16 groups, 183 items. Checked
cell by cell against the source afterwards (~9,800 cells). Two gaps and one
caveat:
- **Files not copied**: 1,071 attachments (~3 GB) on 176 items. The API
  can't copy files by value; they'd need to be downloaded and re-uploaded.
- **One value lost**: CL3698's Sales Rep (Tanner Wach). Monday refuses to
  assign that user, who is no longer visible to the account and is most
  likely deactivated.
- **Point-in-time copy**: Design & QA was being edited during the run
  (CL2669, S3855 changed and s7209 deleted after the copy). Nothing syncs
  the two boards.

`MONDAY_API_KEY` (Jennette Boone) **can write to this board**, unlike the
old Plex Import Board `18430735110`, which still 403s on a seat-type
restriction. Added to `.env` as `MONDAY_BOARD_PLEX_IMPORT_V2`.
## 2026-09-22 (board) - the Migration Board rebuilt for someone who has never opened BigQuery

### Changed - the board is generated from `scripts/board/`, not hand-edited
`board_data.py` holds the content, `build_board.py` the layout. The split is
the point: the content changes weekly, the design does not, and every previous
update was a patch script in a scratchpad that nobody else could re-run.

Published to the **same URL** as always (v25). Jennilyn and others hold that
link.

### Changed - written in plain English, front to back
Emilio's ask, and a fair one: the jargon had become a barrier to reading our
own status page. Every tile now leads with **the question it answers** rather
than the view that answers it, and each card shows the whole migration in one
line - **the source feeding it today, then the Plex view replacing it**.

Three things are new:

- **A 30-term glossary with search**, each entry saying what a term means and
  then *why it matters here* - which is where the traps actually live.
  `Encapsulating` vs "Encapsulation", Scrap vs Destroy, Sales vs Revenue, why
  no goal can come out of an ERP.
- **Today's source, with the audit's own verdict on it.** Taken from
  `score-card-reference/Vox_Scorecard_Data_Catalog.md`: of 26 sources, five are
  **broken** and ten **flagged** today. `Production_Daily` feeds 21 charts;
  `vw_shipping_daily_snapshot` feeds 7 and is broken. Knowing what we are
  replacing is half the argument for replacing it.
- **Real vs test data, marked per tile.** After the injector ran, several tiles
  carry rows that are ours, not Vox's. A test figure presented as a business
  figure is worse than a blank tile, so each card says which it is.

### Removed - the progress bar and the andon board
Both counted views rather than readiness, and both encouraged reading a number
instead of the question under it. What replaced them: three "start here" cards
that say what is happening, how to read a tile, and what real-vs-test means.

## 2026-09-22 (test data) - prove the tiles, and one view that was never empty

### Added - `scripts/scorecard_test_data.py`, inject and delete on demand
A blank tile has two causes that look identical from a dashboard: the view is
wrong, or the tenant has nothing of that kind. This puts rows underneath so the
two can be told apart. `--inject`, `--delete`, `--status`, `--recipes`,
`--days`; five recipes (production, shipping, cycle_count, activity, safety).

**The rows are deliberately not realistic** - shaped to satisfy the views, not
to resemble the business - and the script says so in its own output.

**Removal is guaranteed twice over**, because a cleanup that depends on a
record of what was written fails exactly when it matters: every row carries a
marker (integer keys from 990000000, text keys prefixed `ZZTEST`) and
`--delete` runs those predicates rather than reading the manifest, so it works
from a machine that has never injected anything. The manifest backs `--status`
only. The nightly tenant wipe is a third net. **It refuses to run against
PlexProd** - not a flag, not an override.

Two bugs in its own first run, both fixed and both worth the note: the manifest
INSERT was built by f-string and broke on a predicate containing `LIKE '99%'`
(quotes now escaped like any other literal), and the production recipe took
*every* work centre in the tenant - 836 rows to prove what 171 proves.

### Fixed - `part_cycle_count_report` was UNQUERYABLE, not empty
It cast `Cycle_Inventory_Date` - INT64 nanoseconds - straight to TIMESTAMP.
BigQuery rejects that cast pair outright, and SAFE_CAST does not rescue an
illegal cast, only a failed parse, so **the view failed to parse and every
query against it errored**. It was written while the raw table was still
all-STRING (autodetected at 0 rows) and broke silently the moment real typed
rows landed - the same 2026-08-23 typing change that fixed other things.

It had been recorded as "0 rows - nothing counted yet on the tenant". A status
check that reports row counts cannot tell those apart, which is exactly why the
injector earns its keep. Now returns real figures: **9 locations, 56 items,
82.1% accuracy** on injected counts.

### Verified after injection
`shipping_daily` 1 to 14 - `shipping_revenue` 5 to 19 -
`shipping_pending_revenue` **0 to 4** - `production_monthly_by_workcenter_group`
1 to 9 - `production_vs_goal` 1 to 9 - `quality_fpy_by_area_month` 1 to 9 -
`inventory_avg_daily_usage` **0 to 1** - `part_cycle_count` **ERROR to 1**.

Left uncovered on purpose: `inventory_valuation_total_report` (needs three
joined cost tables, and a fabricated cost is the one number here that would
mislead rather than prove) and Quality (22 real records already).

## 2026-09-22 (goals) — one goals pipeline, not two

### Changed — the three vs-goal reports read the resolver; the `v2_` copies are gone
There were two of everything: `revenue_vs_goal_report` read the legacy
`scorecard_goals` table, and a generated `v2_revenue_vs_goal_report` read the
resolver — same for sales and production. Six views, two goal sources, one
resolver, and an Apps Script feeding each table. That shape was right while
Looker Studio migrated one tile at a time, and stopped being right once there
was nothing left to migrate.

Now: the three original reports read `scorecard_goals_resolved` (renamed from
`v2_scorecard_goals_resolved`), the three `v2_` copies are deleted from every
config, and **nothing reads a goal table directly** — the "newest edit wins"
dedupe lives in exactly one place.

**This is a fix as well as a simplification.** `sales_vs_goal_report` and
`revenue_vs_goal_report` had been reading the legacy table only, so a goal
entered in the web app did not reach them at all — you had to know to look at
the `v2_` copy instead. Verified after the change in PlexTest: the resolver
returns **80 goals — 12 from the app, 68 from the legacy table**, and
`revenue_vs_goal_report` now shows the app's revenue goal where it previously
showed none.

### Removed — `deploy/goals_sheet_to_bigquery.gs` and `scripts/gen_v2_goal_views.py`
The legacy sheet-to-BigQuery writer and the generator that produced the `v2_`
copies. Neither has a job any more.

⚠ **Deleting the file does not stop the deployed Apps Script.** The old
project still has to be disabled by hand, or it will keep truncating
`scorecard_goals` on its schedule.

### Added — `importLegacyGoals()` in the manual-data app
The one manual step that finishes this. `scorecard_goals` still holds **68 real
sales rep-month goals — the only copy** — and they cannot be moved by writing
to BigQuery, because `scorecard_goals_app` is rebuilt from its sheet on every
push. So the import goes through the sheet: it reads the legacy table, appends
every row to the app's goals tab marked with its origin, **skips keys the app
already has** so a since-edited goal is never overwritten, and pushes once at
the end rather than per row.

Afterwards: confirm `goal_source = 'sheet'` returns 0 rows, then the legacy
branch can be deleted from the resolver and `scorecard_goals` dropped. Until
then that table stays.

### Still to do by hand
- **Drop the four orphaned `v2_*` views** in both datasets — they are out of
  every config so nothing refreshes them, but they still exist. The local
  permission classifier blocked the DROP.
- Run `importLegacyGoals()`, then disable the old Apps Script project.

## 2026-09-22 (last) — turnaround standards get a table, sales reps get a roster

### Added — `turnaround_standards`, in both datasets
Created by hand in `PlexTest` and `PlexProd`; **not** Terraform-managed and
**not** written by the ETL, the same arrangement as `scorecard_goals` and for
the same reason. Jennilyn edits it directly in BigQuery.

This is the other half of dropping the web-app tab earlier today: the
standards needed a home, and a form was the wrong one for numbers that change
about never. A table she can edit is the right shape.

⚠ **It must exist or `quality_turnaround_time_report` fails to create**, which
looks like a broken report rather than a missing dependency — the exact trap
`scorecard_goals` sets for the three vs-goal views. An EMPTY table is fine and
reads as `none set`. Rebuild DDL, how to add a standard, and the two things to
get right: `docs/reports/turnaround_standards.md`.

### Changed — turnaround time measures each record against its standard
`quality_turnaround_time_report` gains `stock_type`,
`performance_standard_days`, `bonus_standard_days`, `standard_source`,
`met_performance_standard` and `met_bonus_standard`.

Three decisions worth keeping:
- **A standard is chosen by WHEN the problem happened**, not by which row is
  newest. A change is made by adding a row, and the newest row effective on or
  before that record's month wins — so a standard starting in December is
  correctly not applied to a September problem.
- **There is a catch-all.** 12 of 22 live NC records have no part, and
  therefore no stock type; without a blank-stock_type row they would get no
  standard at all. `standard_source` says `stock type` or `catch-all`, so a
  fallback number is never mistaken for a type-specific one.
- **Met/missed is NULL, not false**, while a record is open or no standard is
  set. "We don't know yet" and "missed it" are different answers.

Proven end to end in `PlexTest` with three PLACEHOLDER rows (clearly labelled,
to be deleted when the real figures arrive): record 9 takes the catch-all
30/15 and meets both; record 2 takes the `Raw Materials` 7/3, meets
performance at 5 days and **misses bonus** — so the flags discriminate rather
than always agreeing. `PlexProd` left empty on purpose.

⚠ **`stock_type` assumes the sheet's "Item Stock Type" means Plex's
`Part_Type`** (Components, Raw Materials, Semi-Finished Goods, Finished Goods,
WIP, Supply, Inspection). Closest thing on the part master — there is no
`Stock_Type` column — but unconfirmed against the sheet.

### Added — `sales_reps_report`, and the goals dropdown now reads it
The manual-data app built its sales-rep list from `DISTINCT sales_rep FROM
sales_mtd_summary_report` — reps who already sold something **this month**. A
new or quiet rep never appeared, so they could not be given a goal, which is
exactly where a goal matters most.

Now reads Plex's `Inside Sales` role roster (`Plexus_Control_v_Role` +
`Plexus_Control_v_User_Role`, added to both `sales_orders` configs — 26
extractions, 29 views each). Matched on the role **name**, not its key.

**Verified after deploying:** 13 reps, and **all 7 who carry a real goal today
are among them** — nobody is lost, six become reachable. Two findings fell out
of it: `Inside Sales` has `Commissionable = FALSE`, so that flag is NOT how Vox
marks a sales role and filtering on it would have returned nobody (it is
published rather than used); and one existing goal is scoped to the literal
string **"Sales Representative"**, which is not a person and matches nothing —
invisible while the dropdown only listed reps with sales, and somebody's to
clean up.

The loader falls back to the old source if the new view is not in the dataset
yet: an empty dropdown is worse than a short one.

### Deployed
`terraform apply` — 3 added, 3 changed, 2 destroyed; `plan` after it reports no
changes. Test jobs for both pipelines run and **every view verified by
querying it**, not by exit code. Prod views pick the new SQL up on tonight's
scheduled runs. The web app still needs Deploy > Manage deployments > New
version — nothing in Apps Script has shipped yet.

## 2026-09-22 (later) — Manual Data app reworked from the Sep-21 call

### Fixed — the app would have broken the goal views on its first real push
`COMMON_FIELDS` stamped every row with `submitted_by` / `submitted_at`. The
live `scorecard_goals_app` table carries **`updated_by` / `updated_at`**, and
`v2_scorecard_goals_resolved` both selects them and dedupes on
`ORDER BY updated_at DESC` — the "newest edit wins" rule the whole
append-only design rests on. Pushes are `WRITE_TRUNCATE` with an explicit
schema, so the first real save from this app would have replaced that table
with columns the resolver does not have, taking out `revenue_vs_goal`,
`sales_vs_goal` and `production_vs_goal` together.

Nothing had hit it yet only because nobody has entered a goal through the app.
Jennilyn's plan on the 2026-09-21 call was to start doing exactly that —
*"if we can get it connected in writing, we can put in our current goals and
then just go ahead and start using this"* — so this was about a week from
being discovered as three broken tiles. Renamed to match the table. Verified
against PlexTest 2026-09-22.

**If the sheet tabs already carry the old headers, re-run `setupSheets()` or
rename those two cells** — `appendToSheet_` maps values onto header names, so
a stale header writes blanks rather than failing.

### Removed — the Turnaround standards tab
Asked directly on the call: *"should we keep the tab for turnaround
standards?"* — *"I don't think we need it… they don't change those standards
very much."* This **reverses the 2026-09-11 decision** to move them into the
app with restricted edit access, so the reasoning is recorded rather than just
the outcome: a form earns its keep on numbers that change often enough that
chasing someone to edit a table is worse than giving them a form. These change
about never, and the edit-access worry that came with them — they are
bonus-bearing — is a cost rather than a benefit.

⚠ **Consequence, stated because it is easy to miss:** the standards now have
no home in BigQuery at all. `quality_turnaround_time_report` publishes
turnaround actuals with nothing to measure them against; the comparison stays
wherever the Monthly TAT Analysis sheet lives. The open "who may edit the
form" decision narrows to goals.

### Changed — goals split into three tabs, storage untouched
*"Maybe instead split out the production goals and the sales goals into two
separate tabs."* Done as **Sales goals / Production goals / Revenue goal**,
each pinning `metric` so the goal-type dropdown disappears — the tab is the
choice. Revenue keeps its own tab because it is company-wide by definition and
deliberately a different number from Sales; folding it into Sales would imply
they are the same thing.

**A presentation split only.** A dataset here is 1:1 with a sheet tab and a
BigQuery table, and pushes are `WRITE_TRUNCATE`, so three real datasets would
mean either three tables — breaking every view that reads
`scorecard_goals_app` — or three tabs racing to truncate one. "Recently
entered" filters to the pinned metric so each tab lists only its own rows.

### Added — each form shows what is already saved, above the fields
Pick a goal type, month and scope and the current value appears with who last
changed it; the incidents tab shows the most recent incident. Jennilyn's
reasoning is the design: *"if they're editing say a December goal, they're not
really going to have visibility into seeing what December's goal is in
BigQuery to know that it's right or wrong without asking me."*

Read-only, and it **never blocks a save** — a failed lookup hides the panel and
the form still works. "Nothing saved yet" is its own message rather than a
blank, because on a safety log an empty answer means something specific.

### Still open from the same call
- **Which roster defines "sales rep"** for the goals dropdown. It reads
  `DISTINCT sales_rep` from `sales_mtd_summary_report`, so a rep with no
  qualifying sale this month never appears. Plex's `Inside Sales` role
  (Role_Key 55369) holds all 7 reps who currently carry a goal plus several who
  don't — still waiting on Jennilyn before wiring it.
- **Deploying it.** Apps Script has no version control and saving the code does
  not update the live app: Deploy > Manage deployments > New version. The part
  costs removal from 2026-09-16 is still not live either.

**Not a code change to the pipeline** — nothing here ships via Terraform or
Cloud Build.

## 2026-09-22 — the Quality reports were reading the wrong Plex table

### Fixed — `Quality_v_Problem` is the classic table; Vox writes `Quality_v_Problem_2`
Jason and Sheldon's Problem Control session produced 22 real records. None of
them reached BigQuery, and the reason was not the tenant: **Plex has two
problem tables and Vox records on the UX screen, which writes
`Quality_v_Problem_2`.** Every Quality report here had been built on the
classic `Quality_v_Problem`.

Verified live 2026-09-22 against `vox.test.odbc.plex.com`: **19 records in the
Problem Control UI, 22 rows in `Quality_v_Problem_2`, 0 rows in
`Quality_v_Problem`.**

**Nothing ever said so.** The extraction genuinely succeeded — it asked the
right question of the wrong table — so the job exited 0, the run email said
success, and the zero-row guard logged `0 rows for raw_Quality_v_Problem →
existing table left untouched`. Four reports had therefore returned 0 rows
since the day each was built, which read exactly like "the tenant has no
quality data yet", and was written down as that more than once.

Repointed `quality_nonconformance_view.sql` and
`quality_turnaround_time_view.sql` at the UX table; `quality_cost_by_category`
and `quality_disposition_cost` follow automatically, being thin views over the
nonconformance report. Row counts in `PlexTest` after the fix: **nc 22, tat 22,
cost-by-category 9, disposition-cost 1, deviations 2** — verified by querying
each view, not by trusting the exit code.

The classic table stays extracted on purpose, so anything ever recorded on the
classic screen still lands somewhere and the contrast between the two raw
tables stays visible.

### Added — `Quality_v_Problem_2` + `Quality_v_Problem_Form` extractions
Both configs (`reports/quality_nonconformance.yaml` and its `reports/test/`
twin, 13 extractions each). The form lookup is what makes **Problem Form**
readable — and Problem Form turns out to be the dimension Quality actually
classifies by: Material Destruction (3), Non-Conformance Form (3), Risk
Assessment (4), System Audit CAR (4), 8D (3), Complaint Form (2), Initial
Problem Report (2), 5P (1).

New columns on `quality_nonconformance_report`: `problem_form`,
`problem_form_key`, `recorded_date`, `due_date`, `quantity_scrapped`,
`champion_key`, `department_no`, `building_key`, `workcenter_key`, `job_key`,
`job_op_key`, `recurrence`, `root_cause_response`, `response_action`, and
`brief_description_html` beside a tag-stripped `brief_description` (the UX form
is rich text — records arrive as `<p>**TEST**&nbsp;…</p>`).

**`corrective_action` is gone**, and that is a real difference rather than an
omission: Problem_2 has no such column. Corrective and preventive actions are
their own records in the Problem Action family, one row per action, which is
what lets an 8D carry several. Not extracted yet — add when action-level
reporting is actually wanted.

### Changed — turnaround time ships BOTH clocks instead of choosing one
The Problem-Date-vs-Entered-Date decision has been open since 2026-09-11 and
stayed theoretical while the table was empty. `Problem_2` carries both, both
populated, genuinely different (Problem_Date is usually date-only,
Recorded_Date a precise timestamp). `turnaround_days` keeps its existing
meaning so nothing downstream shifts, and `turnaround_days_from_recorded`,
`reporting_lag_days` and `closed_on_time` (against Plex's own due date, a
column the classic table did not have) sit beside it. **The decision is still
needed** — it picks which column the scorecard reads — but the report is
usable either way in the meantime.

### Found — three things that block the Quality $ tiles, none of them ours
- **`Cost` is 0.0 on all 22 records.** The value is being typed into the
  description instead: records 6, 11 and 17 read `1.5`, `600` and `$2305.57`
  and nothing else. Destruction $ / Rework $ / Deviation $ read $0 until that
  changes. Not papered over — a fabricated cost is worse than a visible zero.
- **`Final_Disposition` is blank on all 22**, including the one Closed record.
  Destruction is recorded by choosing the Material Destruction *form*, not by
  dispositioning material as Scrap. `quality_disposition_cost_report` is
  deliberately **not** repointed at the form: which of the two Vox means is
  Quality's to answer, and switching it quietly is how the accounting-approval
  tile went silently dead in the first place.
- **Deviations are linked to nothing.** Sheldon created 2 in Plex's built-in
  deviation module (both "machine damaged", 585 pieces) and all four junction
  tables — Job, Part, Problem, Workcenter — are still empty. Linking them to a
  job is his next test, from the 2026-09-22 meeting.

Also worth recording from that meeting (`meetings-reference/sep-22/`): the
custom **CAPA Report** and **Deviation Form** both fail to submit, and Material
Destruction / Risk Assessment lose data when heavily filled in. Sheldon meets
Justina Thursday about the forms and will ask his manager whether the custom
deviation form can be retired in favour of Plex's built-in module.

### Deployed
SQL and the test config pushed to GCS and the test job run twice (the first
run caught `Corrective_Action` not existing on Problem_2 — the view-retry
safety net reported it cleanly instead of failing the run silently).
**`terraform apply` still needed for prod** — `reports/quality_nonconformance.yaml`
and both SQL objects are Terraform-managed.

## 2026-09-21 — Label Design part attributes: NULLIF fix, five new attributes

### Fixed — empty-string attribute values leaking as `''` instead of `NULL`
`reports/sql/label_design_view.sql` pivoted `pa.Value` raw. Verified against
live BigQuery: all 28 rows in `raw_Part_v_Part_Attribute` (14 parts ×
Allergen + Hazardous) carry an **empty string**, not NULL — so every
`part_*` column emitted `''`. Downstream that reads as "filled in, but
blank", and would have let the not-yet-built Monday push service overwrite a
hand-entered value with an empty one. Every branch is now
`NULLIF(TRIM(pa.Value), '')`; re-verified against live BigQuery to return
`NULL`.

### Added — five more part-attribute columns
Jennilyn added five attributes in Plex since 2026-09-16, present in **both**
PlexProd and PlexTest with identical catalogs (so: real production config,
not test-tenant scratch): `California PDP`, `Prop 65 Requirement`,
`Trademark`, `Bottle Material`, `Material Classification`. All ten are now
pivoted — new columns `part_bottle_material`, `part_california_pdp`,
`part_prop_65_requirement`, `part_trademark`,
`part_material_classification`. All values are blank today, so all ten read
NULL; they are exposed rather than pre-selected because this build has
already been burned once guessing attribute names.

`Bottle Material` existing Plex-side resolves the one mapping there was a
confident answer for — Ashley confirmed 2026-09-16 that Monday's Bottle
Material (container: HDPE/PET/Glass) and Plex's Printing Material (label
stock) are different concepts, and Plex now carries both separately.

### Changed — attribute keys are not stable; the doc said otherwise
`Printing Material` moved from `Attribute_Key 7427` to `7432`, and `7427` is
now `California PDP`. The pivot was unaffected **only** because it joins on
`Attribute_Name` — a key-based pivot would have silently reported California
PDP as the printing material. Noted in the SQL comments as a rule, not an
observation. `label-design/STATUS.md` and
`docs/reports/label_design_report.md` updated; the previously documented
proof example (`part_allergen = "Yes"` on `Part_Key 11003458`) is gone, that
part is no longer in the table at all.

SQL-only change — ships via `terraform apply`, not Cloud Build. Dry-run
validated; **not yet applied.**

## 2026-09-17 (later) — dev/dev-label-design/dev-scorecard branches, deploy preflight check

### Added — `scripts/deploy_preflight.sh`
Neither `terraform apply` nor `gcloud builds submit` (`docs/OPERATIONS.md`
Step 5) checks git branch or working-tree cleanliness before deploying —
each one deploys exactly whatever's on local disk. With work now split
across `dev`/`dev-label-design`/`dev-scorecard` branches (see below), that
gap became a real risk: running either deploy command from a feature
branch would silently ship the feature branch to prod. This script exits
1 with an explanation unless the current branch is `main` and the working
tree is clean; `docs/OPERATIONS.md` and `CONTRIBUTING.md` both now say to
run it first, every time.

### Added — `dev`, `dev-label-design`, `dev-scorecard` branches
Per Emilio: separate branches per project for clearer, filterable commit
history (Label Design and Vox Scorecard work had been landing
interleaved on `main`, same root problem as the status-doc tangle fixed
earlier today). `main` stays the only branch anything deploys from — see
`CONTRIBUTING.md` for the full breakdown of what lives on each branch and
why they're long-running rather than short-lived topic branches.

## 2026-09-17 — Label Design status file moved out of repo root; two VS Code workspace files added

### Changed — `sep-14-brief-and-pending-items.md` → `label-design/STATUS.md`
Moved with `git mv` (history preserved). The old repo-root location didn't
self-label as Label Design-specific, unlike the Scorecard side's
`score-card-reference/` — this is exactly how a Claude session nearly wrote
Scorecard content into it mid-session before catching itself. All
cross-references updated (`label-design/README.md`,
`label-design/monday_board_catalog_tablero_nuevo.md`, this repo's `README.md`).
Explicitly **not** fixed with a new repo or a new git branch: the code was
never actually tangled (every pipeline, Label Design included, shares one
`main.py` ETL engine, one Terraform config, one Docker setup — splitting
would mean forking that shared engine for no benefit), and a branch just
relocates the same confusion from "which file do I update" to "which
branch am I on," which is worse for two efforts meant to coexist
indefinitely rather than merge back together.

### Added — `label-design.code-workspace`, `scorecard.code-workspace`
Two VS Code multi-root workspace files, both pointing at this same single
repo (no code or git split — it's a display/search filter only), each
hiding the other project's exclusive folders (`label-design/`,
`label_design_service/`, `deploy/label_design_sync/` vs.
`score-card-reference/`, `deploy/manual_data_app/`,
`deploy/goals_sheet_to_bigquery.gs`) via `files.exclude`/`search.exclude`.
Shared infra (`main.py`, `terraform/`, `reports/`, `docs/`) stays visible in
both, since both genuinely depend on it. Lets the two projects be worked on
in separate VS Code windows without one cluttering the other's
explorer/search.

## 2026-09-16 (evening) — Manual Data app: part costs removed, two dropdown bugs

### Fixed — `Code.gs`'s `partNumbers` option loader queried a table that never existed
`part_v_part.Part_Number` was never a real table/column — the extracted
part master is `raw_Part_v_Part.Part_No` (confirmed against both PlexTest
and PlexProd). This was the cause of the Part Costs tab's "Could not read
the list for this field" error. Moot now — see Removed, below — but the
same wrong-name bug pattern is worth remembering if another dropdown reads
Part_v_Part again.

### Removed — the `part_costs` manual dataset
Never a real requirement — Emilio's own words in the 2026-09-16 Emilio/
Jennilyn meeting (`meetings-reference/sep-16/`) framed it as "just a
fallback, the cost will still be handled by Plex." Jennilyn's actual plan,
from that same meeting: inventory valuation is unit cost × on-hand
quantity across roughly 5,500 customer finished goods + a few hundred
products + under ~2,000 purchased parts holding a $ value; Plex's own
costing (`Part_v_Snapshot` / inventory valuation) is expected to populate
via a NetSuite-Celigo integration, on some schedule — mechanism (one-time
upload vs. periodic sync) still undecided, pending Accounting. For
scorecard reporting specifically, Revenue and Inventory Value are pulled
from NetSuite **for now, as an interim measure** while Plex costing stays
empty — not framed as a permanent replacement for Plex, and NOT a decision
that resolves Deviation $/Rework $ costing (a separate, still-open
question — those come from a `Cost` field on Quality's nonconformance
records, untouched by this meeting). A human retyping cost numbers into a
fourth manual-entry table would only drift from both of those real
sources. Removed from `Code.gs`'s `DATASETS` registry, along with the
now-unused `partNumbers` option loader.

## 2026-09-16 (later) — Monday test board built for the standalone push service; two API bugs found

### Added — `scripts/replicate_board_columns.py`
Copies column title+type+status-labels from one Monday board to another via
the API, so a test board can structurally mirror prod ("Design & QA",
`18395121955`) without touching prod itself. Built to prep "Tablero nuevo"
(`18430931138`, Emilio's personal dev-sandbox board) as a realistic target
for testing the new standalone Label Design push service, since permissions
on the originally-intended "Plex Import Board" (`18430735110`, in the real
Voxnutrition workspace) turned out to be write-restricted for the token
available today. Full writeup, including the fix for a "Reason Code" /
"Bottle Material" title-collision-with-wrong-type gap, in
`label-design/monday_board_catalog_tablero_nuevo.md`.

### Fixed — two real Monday API bugs, neither documented anywhere obvious
1. `create_column`'s `defaults` for a `status` column needs `{"labels":
   {"0": "A", ...}}` (dict), not `{"labels": ["A", ...]}` (array) — the
   array form is silently accepted (returns a valid column id, no error)
   but produces a column with a single **null**-labeled option. 39 columns
   were created looking successful before this was caught by reading
   `settings_str` back and finding every label null.
2. `create_column` cannot set more than ~20 labels in one call (confirmed
   by bisection; individually every label text was valid). No API path
   exists to add more afterward — `change_column_metadata`'s
   `ColumnProperty` enum is only `title`/`description`, and
   `change_column_value` with a not-yet-existing label errors
   `missingLabel` rather than auto-creating it. Prod's real 33-option
   "Reason Code" column can't be mirrored byte-for-byte via the API; the
   test board's version deliberately holds only the 6 options
   `label_design_service/reason_code.py` actually needs.

### Changed — `.env`
Removed a duplicate `MONDAY_API_KEY` line (two different tokens under the
same name — the env loader was silently using whichever came last). Split
into named vars: `MONDAY_API_KEY` (Voxnutrition company workspace — but
Jennette Boone's *personal* token, not a service account; flagged as a
follow-up risk for anything scheduled) and `MONDAY_API_KEY_PERSONAL_DEV`
(Emilio's own dev sandbox, used for the Tablero nuevo work above). Also
corrected/renamed the three `MONDAY_BOARD_ID_*` vars after discovering the
catalog doc's board id and an earlier `.env` version disagreed — verified
against the live API which board is actually which.

## 2026-09-16 — Part Attributes, and a syntax bug the last dry run never actually caught

### Fixed — `label_design_view.sql` had an orphaned `),` since the 2026-09-15 release-collapse edit
Found while adding new CTEs, before building on top of it: an extra closing
paren + comma sat right after the `dates` CTE, with nothing open left to
close. That edit's own dry run never actually completed (blocked by the
`gcloud auth login` wall) — it was only read through by eye afterward, which
missed it. Confirmed as a real defect (not a misreading) with a local
paren-balance check, then fixed. Live BigQuery verification is still blocked
on the same auth wall as of this writing; every new column name below was
cross-checked against `catalog/full_schema_catalog.csv` by hand instead.

### Added — `part_bottle_material` and `part_regulatory` to `label_design_view.sql`
Per Jennilyn: read from Plex's generic Part Attribute system
(`Part_v_Attribute` + `Part_v_Part_Attribute`, both extracted here for the
first time — added to both `reports/label_design.yaml` and its test twin)
instead of a human typing Bottle Material into Monday by hand every single
order, which is what happens today (checked a live 2-week board pull: **113
of 113 orders** had it manually filled in).

Joined on `Part_Key` — Plex's own internal part identifier, present directly
on `Sales_v_PO_Line` — not `Customer_Part_Key`/`Customer_Part_No`. This
sidesteps the "seven part number vs. nine" ambiguity Jennilyn herself
raised in the 2026-09-14 meeting; `Part_Key` is Plex's stable internal key
regardless of which customer-facing numbering format is in play.

**Confirmed with Jennilyn, both in the meeting and again explicitly this
session: one value per attribute per part.** A part needing more than one
regulatory flag at once (Prop 65 *and* Organic) is handled by Plex's own
dropdown carrying pre-defined COMBINED entries ("Prop 65 + Organic", "Prop
65 + Organic + GMO-Free") as their own single selectable value — not by
multiple attribute rows. That combined string is passed through completely
untouched, deliberately not parsed or split on `" + "`: a new combination she
adds tomorrow is a new string this has never seen, not a new format to
handle.

**Not yet real data.** Jennilyn: *"we haven't made any [part attributes] to
apply to labels yet."* Both new columns read NULL until she uploads test
values — the extraction and join are built ahead of that on purpose, so
there's nothing left to do the moment she does. The attribute names matched
on (`'Bottle Material'`, `'Regulatory'`) are our best guess, flagged
in-line in the SQL for confirmation against her real setup.

**Deliberately deferred, not decided:** which Monday column
`part_regulatory` eventually feeds. Monday's own "Regulatory Status" is a
fixed-option dropdown with no compound entries — a string like "Prop 65 +
Organic" won't fit it. The plain-text "Prop 65" column (currently blank on
every order) is the likely home instead, but that's a push-side decision for
later, not something the extraction needed settled today.

### Fixed (same day) — the two guessed attribute names were both wrong; corrected against real data
`gcloud auth login` unblocked verification a few hours after the above was
written. Running the (fixed) view against real BigQuery — not just a local
paren check — turned up something the guess couldn't have caught: Jennilyn
had **already uploaded real test data** (`Part_v_Attribute`: 5 rows,
`Part_v_Part_Attribute`: 28 rows) linked to real test order Part_Keys. The
view created successfully, but `'Bottle Material'` and `'Regulatory'` — the
two names guessed at, in the entry above, before any real data existed —
**matched nothing**, because neither attribute exists. The real five:
**Size, Allergen, Hazardous, Certifications, Printing Material.**

Rather than re-guess a mapping onto two buckets, all five real names are now
exposed as their own columns — `part_size`, `part_allergen`,
`part_hazardous`, `part_certifications`, `part_printing_material` — since
naming them is just reading a fact from Plex, not a business decision. Which
of the five (if any) feeds which *Monday* column stays open, same as the
Prop 65 question above; most of her 28 rows still carry a blank `Value`, so
there isn't enough populated data yet to infer that mapping from content.

**Verified with a standalone proof query, not just "the view compiled"**:
`part_allergen = "Yes"` on `Part_Key 11003458` — the one value she's
actually populated so far — comes through the pivot correctly.

### Fixed — the orphaned `),` from the entry above, confirmed against live BigQuery
The local paren-balance check said it was fixed; today's re-run against real
BigQuery is what actually proves it — the view now creates without error,
twice, across both the wrong-name and corrected-name versions of this SQL.

## 2026-09-15 — dropping the Sheet, a Job-Note parser, and a catalog correction

### Decided — Label Design's next phase: no more Google Sheet middleman
The team wants the Sheet gone entirely from the Plex → Monday flow. Settled
so far, nothing built yet beyond the two pieces below:
- **A new standalone service** (Cloud Run Job + Cloud Scheduler, matching
  every other pipeline component here), not an extension of the existing
  Apps Script.
- **A new BigQuery audit table** replaces the Sheet's role as the visible
  record of what happened, once nobody can just open a tab and look.
- **Dedupe moves to a hash-based LCR.** Going forward, the Monday `LCR`
  column itself holds a SHA-256 hash (first 12 lowercase hex chars) of
  `order_number + customer_part_no` — reusing the existing column rather
  than adding a new one. A run recognizes "already on Monday" by finding a
  matching hash there. Verified safe against all 4,500 real historical LCR
  values first: none are lowercase hex, so a hash can never collide with an
  old hand-assigned code (`LCR A00980`, date-suffixed codes, etc.). Cutover
  date **10/19** (Jennilyn) — items already on the board before then are
  left alone, never reconciled. Open edge case, not yet resolved: the
  view's 14-day rolling window means an order dated just before 10/19 could
  still appear in BigQuery's output well after the cutover, added to Monday
  the old way (no hash) — the new hash-only check wouldn't recognize it and
  could create a duplicate.

### Added — `label_design_service/reason_code.py`
Job Note → (Reason Code, Memo) split, confirmed against a real example
(Emilio): a Job Note's **first character** is the reason code (1-6, mapped
to real Monday option indices — several near-duplicates on the Reason Code
dropdown made hand-confirming each one necessary rather than text-matching);
everything after it, separator stripped, is the Memo. An unrecognized first
character (not 1-6, or no leading digit at all) consumes nothing — the whole
note goes to Memo untouched and no Reason Code is set. That last part matters
in practice: checked all 164 real non-blank Memo values from a live board
pull and **none** currently start with a digit, confirming this is a
going-forward convention, not something already in the data.
21 checks in `test_reason_code.py`, including the real confirmed example
(`"3 Update to current V code. Standard Label."` → New label design (Vox
design) + memo `"Update to current V code. Standard Label."`).

### Added — `scripts/pull_monday_board_snapshot.py`
Pages through every item on the Design & QA board (206 total, 113 in the
last 14 days by the `Date` column), writes a CSV for review. Read-only,
one paginated GraphQL query. Output is gitignored, same PII treatment as
the historical Label Design export — real customer names/emails/phones.

### Fixed — `label-design/monday_board_catalog.md` said "43 columns"; it's 61
Found while re-verifying for accuracy: a fresh pull structurally diffed
against the committed catalog — every title, id, type, and status/dropdown
option value — came back identical. The board was never stale; "43" was a
wrong count in the prose, most likely confused with Reason Code's own ~40
options. Content was correct the whole time; only the summary number was
wrong. Corrected in place with a dated note rather than silently rewritten,
per this file's own convention of not editing history quietly.

## 2026-09-14 — non-technical team guide, and a written working agreement on patch size

Added [deploy/label_design_sync/TEAM_GUIDE.md](deploy/label_design_sync/TEAM_GUIDE.md)
— a plain-English "how do I use the two buttons" doc for the design/sales
team, separate from the technical README (which stays for engineers), plus
instructions for optionally wiring an on-sheet Drawing button to
`checkForNewOrdersManual` / `pushToMondayAndArchiveManual` (the menu built by
`onOpen()` remains the primary, always-available mechanism; a Drawing is
optional and can go stale if copied without its script assignment).

Added root [CONTRIBUTING.md](CONTRIBUTING.md): a short working agreement to
keep future changes as small, targeted patches rather than large rewrites,
and to ask before large speculative investigations — token/compute
efficiency as an explicit, first-class project concern going forward.

## 2026-09-13 — Label Design sync split into two manual/auto steps, with a lock + ledger to make the Push-and-archive step safe

The team asked for two buttons on the sheet — one to check for new orders,
one to push to Monday — but pushing also has to move rows into `historical`,
and the previous single-step `syncNow()` pushed to Monday automatically from
the raw BigQuery snapshot, before Reason Code/Label/Bottle Material/Prop
65/LCR could ever be filled in by a reviewer. Splitting the step properly
meant designing real concurrency and failure-recovery safety, not just adding
a second function.

**Changed** (`deploy/label_design_sync/Code.gs`)
- `syncNow()` split into `checkForNewOrders_()` (core) + `checkForNewOrdersAuto()`
  (still bound to the 10:00/14:00 daily trigger) + `checkForNewOrdersManual()`
  (new menu item). **Check no longer pushes to Monday under any circumstance.**
- New `pushToMondayAndArchive_()` / `pushToMondayAndArchiveManual()` — manual
  only, no trigger. Reads the `MONDAY` tab's *current* values (so hand-typed
  review columns finally reach Monday and `historical`, which they never did
  under the old design), pushes each row to Monday one at a time, then
  archives pushed rows into `historical` and deletes them from `MONDAY`.
- Added a script-wide lock (`withLock_()`, `LockService.getScriptLock()`) around
  every entry point, so Check, Push, and the scheduled trigger can never
  interleave writes to the sheet.
- Added a hidden `_PUSH_STATE` tab acting as a write-ahead ledger: a row is
  recorded there the instant its Monday item is created — the single commit
  point that makes the whole push+archive sequence resumable and idempotent
  after any interruption, without ever re-pushing an already-created Monday
  item or re-archiving an already-archived row. Worst-case failure mode is a
  visible duplicate (row on both `MONDAY` and `historical` briefly), never a
  silent loss.
- `historical` tab write rule relaxed from "never written" to "append-only,
  exactly once per row, only via `appendToHistory_()`, only for
  ledger-confirmed pushed rows, only from `pushToMondayAndArchive_()`" — every
  other write path is still blocked by the pre-existing `assertNotHistory_()`.
- `SHEET_MAP`'s five 'team' columns (`Reason Code`, `Label`, `Bottle Material`,
  `Prop 65`, `LCR`) gained a `field:` so both the Monday push and the archive
  write can read a reviewer's hand-typed values by the same key.
- Added `onOpen()` — builds a "Label Design Sync" menu (Check / Push & Archive
  / Dry run) automatically every time the sheet is opened; no setup step.
- Split run-log entries by `kind` ('check' vs 'push') and updated
  `sendDailySummary()` to aggregate both; Check's technical email no longer
  claims a "pushed to Monday" count (it never pushes); added a separate
  `sendPushEmail_()` for Push & Archive runs.
- `installTriggers()` now binds the daily trigger to `checkForNewOrdersAuto`
  — **existing installed triggers referencing the old `syncNow` name will
  silently stop firing**; `installTriggers()` must be re-run once after this
  deploy.

**Docs** (`deploy/label_design_sync/README.md`) — rewritten to document the
two-button workflow, the lock/ledger safety design, the revised `historical`
rule, and the accepted risk of a rare duplicate Monday item if our own HTTP
call times out after Monday's side already succeeded (no idempotency-key
support on Monday's `create_item`). Added four Mermaid diagrams: system
overview, Check sequence, Push two-phase-commit sequence with a
failure/resume table, and a per-row lifecycle state diagram.

Verified: `node deploy/label_design_sync/test_logic.js` — all 25 pure-logic
checks still pass (the `SHEET_MAP` addition is additive and doesn't change
what's queried or how headers resolve); `node --check` on the full file.

## 2026-09-14 — a `/label-design` hub, and the Monday board's real columns

### Added — `label-design/`
A dedicated top-level folder for this mini-project, requested so it stops
blending into the Vox scorecard reference material the rest of the repo is
about. **A map, not a copy** — nothing was relocated here: `reports/*.yaml`
and `reports/sql/*.sql` are wired into Terraform's GCS `source` paths, and
`deploy/label_design_sync/` isn't referenced by any build tooling but already
had its own working subfolder, so moving either would cost real risk for no
benefit. `label-design/README.md` is the index; everything else links out to
where the working files already live.

### Added — `label-design/monday_board_catalog.md` and `monday_board_guide.md`
The "Design & QA" Monday board (`18395121955`) was read via a read-only
GraphQL call — nothing written, nothing created — and its full column list
captured before anything gets wired up against it: **43 columns**, with every
status/dropdown column's complete option list (`Reason Code` alone carries
40+, several near-duplicates of each other from what reads as organic growth
rather than a single design pass). The catalog doc has ids and types for
`pushToMonday_()`; the guide doc is the plain-language companion, following
this repo's `docs/reports/` convention of writing for the team, not engineers.

**Three real decisions surfaced that block finishing the Monday push,** none
of them guessed at:
- **Two "Sales Rep" columns** — a fixed-name status dropdown and a genuine
  Monday people-assignment column. `label_design_report`'s
  `sales_rep_primary`/`sales_rep_secondary` are plain text from Plex, so they
  map onto the status column's labels, not the people column (which needs a
  Monday user id). Whoever owns the board should say which is current.
- **Two phone columns** — `Phone` (numbers) and `Phone Number` (text).
  `customer_phone` is a formatted string (`"864-616-8885"`), which only the
  text column can hold without Monday trying to parse it as a number.
- **`Label SKU` is the item's own name**, not a separate column — so a
  created item's title should be the SKU, not `customer — part` as
  `pushToMonday_()` currently builds it.

### Fixed — `label_design_view.sql`: one row per order + customer part
A 2026-09-14 test pull showed order 11 / part 93081-00CHAR2-1 twice, every
column identical except `Due_Date` (9/24 vs 9/25). Traced by elimination
rather than assumed: every other join in the view is a single-row lookup by
key or is already pre-aggregated (`job_notes`), so `Sales_v_Release` is the
only table that can fan a line out into more than one row — and it is
*supposed to*, since it is one row per scheduled release (a split shipment),
not one row per line.

The design queue doesn't track shipment-level scheduling, so the view now
collapses to one row per `order_number + customer_part_no`, keeping the
**earliest** `due_date` across a part's releases (the soonest real deadline)
and a new `release_count` column flagging when a part had more than one, so
the team can go check Plex if the shipment detail ever matters for a specific
row. Implemented as a window-function collapse (`MIN() OVER`, `COUNT() OVER`,
`QUALIFY ROW_NUMBER() ... = 1`) rather than a `GROUP BY`, since every other
column needs to survive the collapse unaggregated.

**Not yet pushed to GCS or re-run** — `gcloud`/`bq` hit the documented reauth
wall (`gcloud auth login` needed, interactively, by a human) when this was
attempted.

### Added — the same fix, in Plex-native SQL
A T-SQL version of the same collapse, matching the dialect and full table
aliasing of the hand-written draft used for direct test pulls against Plex —
`QUALIFY` doesn't exist in T-SQL, so this uses the standard
`ROW_NUMBER() ... WHERE rn = 1` CTE pattern instead. Verified `Terms`,
`Inside_Sales` (`Sales_v_PO`), and `Common_v_Department`/`Department_No`
(`Plexus_Control_v_Plexus_User`) all exist in the schema catalog before
writing it, rather than assuming the draft's column references were correct.

## 2026-09-12 (later) — four latent bugs in `label_design_view.sql`, and the view finally exists

`terraform apply` landed and `plex-etl-label-design-test` ran: all 10
extractions succeeded, and **view creation failed anyway** — the exact
"PARTIAL, exit 0, no view" shape this repo keeps warning about.

The first error named one bad column. Rather than fix-redeploy-repeat, the
whole view was validated at once with `bq query --dry_run` against the live
`PlexTest` tables. That found **four** independent bugs, every one of them
present since the 2026-09-11 build and invisible until now for a single
reason: **no job existed, so the view had never once been created.** Nothing
else in the pipeline reads this SQL, so nothing else could have caught them.

1. **`u.Name` does not exist.** `Plexus_Control_v_Plexus_User` holds
   `First_Name` / `Last_Name` / `Middle_Name`. Now
   `CONCAT(First_Name, ' ', Last_Name)` — the idiom the other five rep-name
   views here already use, and which happens to produce exactly the
   "Tyler Hall" shape the Label Design sheet's own Sales Rep column has always
   carried, so new rows match the 5,000 already archived instead of
   introducing a second spelling of the same person.
2. **`n.Note_Key` does not exist** on `Sales_v_PO_Line_Note` — it is
   `PO_Line_Note_Key`.
3. **`ps.Status` does not exist** on `Sales_v_PO_Status` — it is `PO_Status`.
   Both the SELECT and the `Pending Fulfillment` filter used it. The output
   column stays `order_status`, which is what the Apps Script reads.
4. **The dates were a compile error, not just wrong.** `PO_Date` and
   `Due_Date` land as **INT64 nanoseconds** since the epoch
   (`1750118400000000000` = 2025-06-17) because pandas holds them as
   `datetime64[ns]` and the raw int64 is what gets written —
   `SAFE_CAST(... AS TIMESTAMP)` from INT64 is rejected outright. Replaced with
   this repo's existing three-way `COALESCE` idiom (copied from
   `sales_orders_aging_view.sql`, not reinvented), which reads the value
   whether the column landed as int64 nanoseconds, a date, or a timestamp
   string. That robustness is not theoretical: **an extraction that fetches 0
   rows leaves the column typed from a previous run**, so the same column can
   be INT64 in test and STRING in prod. `ORDER BY` now sorts on the resolved
   date too — sorting the raw int64 works only while it stays nanoseconds.

**Verified, not assumed**: SQL pushed to GCS, `plex-etl-label-design-test`
re-run, and the view queried directly —
`voxdatalake.PlexTest.label_design_report` **exists and is queryable**, for the
first time since it was written. `COUNT(*) = 0`, which is a fact about the test
tenant (3 orders, none of them in Label Design *and* Pending Fulfillment) and
not a defect; the same benign-zero reading this repo has recorded before.

Still to do: `terraform apply` once more so state matches the hand-pushed SQL
object, the Cloud Build for the Vox email branding, and the prod job.

## 2026-09-12 — Label Design: a job to run in, the real sheet, and Vox branding

### Added — the `label_design` infrastructure that was never there
The pipeline shipped 2026-09-11 as configs and SQL with **nothing behind them**
— no Cloud Run job, no scheduler, no GCS config objects. Confirmed against the
live project before building anything: 24 Cloud Run jobs exist and **not one of
them is `plex-etl-label-design`**. So `label_design_report` has never existed,
and the answer to "has the pipeline run yet" is no, not once.

`terraform/main.tf` now carries the missing half — prod and test jobs, both
schedulers each, and the three GCS objects — derived from the
`quality_supplier_returns` block so the env-var list is identical rather than
retyped. Both jobs added to `_ALL_JOBS` in `deploy/cloudbuild.yaml`, without
which they would silently never receive a new image again.

**Twice a day, every day: 9:30 AM and 1:30 PM Mountain** (test :40). Not the
single overnight run every other pipeline uses — this is an operational queue
the sales and design teams work from. The times sit **30 minutes ahead of the
Apps Script's 10:00/14:00 triggers** on purpose, because Apps Script only
guarantees the hour, not the minute; move one side and you must move the other.
Weekends included: orders are entered then, and a weekday-only refresh hands the
team a two-day-stale queue on Monday morning.

`terraform plan`: **9 to add, 0 to change, 0 to destroy** — which also confirms
no other pipeline's prod config had drifted. `terraform validate` and
`terraform fmt -check` clean. Checked `image_url` against a live job first, per
this repo's own rule: `:6c33c51` on both, no drift, so the new jobs come up on
the same image the rest of the fleet runs.

**NOT YET APPLIED** — the local permission classifier blocks `terraform apply`,
so it needs a human. Until then the jobs do not exist and the view cannot be
created.

### Changed — the Apps Script writes the sheet's columns, not its own
`deploy/label_design_sync/Code.gs` wrote 11 snake_case columns of its own
invention. The sheet it writes to has 15 human ones. `SHEET_MAP` is now the
MONDAY tab's real header row, in its real order, and rows are positioned by the
**tab's** header index rather than ours — so someone reordering columns gets
their order respected instead of a scrambled sheet. Real quirks in that export
are handled and tested: the trailing space in `"Label "`, `Phone` on one tab and
`Phone Number` on the other, and six blank trailing headers that are the sheet's
unused columns rather than columns anyone added.

**Unfilled columns are flagged to the team, split by why.** Only one kind is a
to-do: *Reason Code / Label / Bottle Material / LCR* are filled in by a person
during review and blank is permanently correct; *WO Number* and *Item* are ones
Plex could plausibly supply and does not. Reporting both as "blank" every run
would train everyone to skip the section that also carries the real gaps.

**Never writing `historical` is now enforced rather than remembered** — every
write path goes through `assertNotHistory_()`. If the MONDAY tab's layout is
unreadable, rows go to a dated `REVIEW <date>` tab. A new tab, never the
archive, and nothing is discarded.

### Added — a guard on the thing that would quietly cost the most
The sheet says `Sales Order #SO0110212` and Plex says `SO0110212`, so both are
reduced to a token before comparison. **That reduction is the single point of
failure for the whole queue**: if it ever stops matching, every row looks new at
once and the entire archive gets re-imported onto the sheet and onto the Monday
board. `assessKeys_()` watches for exactly that shape — many new rows, *zero*
matches against a non-empty archive — and holds the run back to a review tab
instead of pushing. Rows are kept, not dropped; a person looks first.

### Changed — schedules and recipients
Sync **every day**, summary **Monday to Friday**. Monday's summary covers
Saturday and Sunday too: the window is "since the last summary was sent" rather
than "today", or two days of weekend activity would be reported to nobody.

- **Technical**, every run: Jennilyn, Emilio, `marketing@parasolgroupinc.com`.
- **Summary**, weekdays: Ashley, Kelli, Jennilyn, Emilio, marketing.

### Changed — Vox Nutrition branding on every email
`templates/report.html` rebuilt from Parasol's dark-header layout to the Vox
theme in `assets/css-theme.css` — Leaf Blue bar, Slate Navy Georgia headings,
the Vox wordmark. The Apps Script emails now match, so the pipeline's own emails
and the queue's emails read as one system.

Three things that are easy to get wrong, and were got right deliberately:

- **The logo is an inline CID attachment.** Gmail strips `data:` URIs, and a
  hosted URL would mean making a bucket object publicly readable. Converted
  webp → PNG because **Outlook renders no WebP at all**. A missing logo file
  degrades to alt text and never blocks a send — a failure report still has to
  reach an inbox.
- **Styles are inline attributes, not a `<style>` block** — Gmail strips
  `<style>` from a received message body.
- **The stats row is a table, not flexbox** — Outlook renders `display:flex` as
  a vertical stack, which would break the layout for exactly the desktop readers
  most likely to open it.

`scripts/build_logo_gs.py` regenerates both the PNG and the base64 in `Logo.gs`
(Apps Script cannot read a repo file), so the "generated file" header is true.
The Dockerfile copies **only** `assets/vox-logo.png`, not all of `assets/` —
that directory also holds the 5,000-row sheet exports.

**This is a code change, so it ships via Cloud Build, not `terraform apply`** —
and it has to wait until *after* the apply, because the build's `deploy-all`
step updates every job in `_ALL_JOBS` and the two new ones do not exist yet.

### Added — contact details on `label_design_view.sql`
`customer_email`, `customer_phone`, `customer_part_description`, so the sheet's
Email / Phone Number / Description columns fill from Plex instead of shipping
blank. **Zero new extractions** — both source tables were already joined. These
are account-level details; Plex also holds a per-line contact, and which one the
label team wants has never been asked, so the choice is left visible in the SQL
rather than made silently downstream.

### Added — `deploy/label_design_sync/test_logic.js`
25 checks of the pure logic against the **real** exports in `assets/`, including
all 5,182 historical rows. Verifies that an already-archived order is recognised
across both spellings, that team and gap columns land blank, that rows are
placed by the tab's own column order, and that the alarm trips on a key mismatch
while staying quiet on a busy day and on an empty archive. Needs no credentials
and touches nothing. All pass.

Worth running after any change to `SHEET_MAP`, the tokenisers, or header
resolution — a broken dedupe does not throw, it re-imports the archive.

### Added — `scripts/backup_to_bucket.ps1`
Backs up the repo and, more to the point, the **gitignored files that exist on
exactly one laptop**: `terraform.tfvars`, `.env`, the `assets/` sheet exports,
and any stray local tfstate. A timestamped folder per run plus a `latest/`, with
a manifest naming the commit and listing what was and was not present.

The archive is `git archive HEAD`, not a zip of the working directory, so it can
never smuggle in the very credentials that are gitignored for a reason.

**Run and verified**: 16 objects up, 8 in `latest/`, sizes confirmed by listing
the bucket rather than trusted from the script's own output —
`gs://voxdatalake-terraform-state/plex-to-big-query/backups/`.

One Windows-specific bug found in the first real run and fixed: `gcloud` writes
progress to **stderr even on success**, and PowerShell 5.1 wraps native stderr
in an ErrorRecord, so under `$ErrorActionPreference = 'Stop'` a *successful*
upload killed the script. The preference is now relaxed across each native call
and the outcome judged by `$LASTEXITCODE`, which is the only reliable signal for
a native exe here.

## 2026-09-11 (housekeeping) — audio and the raw glossary out of git

Two files went in with the day's first commit that should not have: the **5.5 MB
meeting recording** and Plex's **6.4 MB glossary export**.

The recording is the one that matters. It is a conversation between named
people, and the transcript and summary sitting beside it carry everything we
act on — there is no reason for the audio itself to travel with a repo that
gets shared.

**Removed from history, not just untracked.** Nothing had been pushed
(`origin/main` was five commits behind), so `git filter-branch` over the three
new commits strips the blobs outright rather than leaving them retrievable.
Commit messages and structure are unchanged; only the hashes moved.

Both files stay on disk and are now gitignored, so the distiller still runs —
verified: same 93 terms, byte-identical output.

`catalog/Glossary-*.csv` being absent from the repo is worth knowing before
someone tries to re-run `distill_glossary.py` on a fresh clone. Noted in
`docs/CHEATSHEET.md`: re-export it from Plex, and the result is deterministic.

## 2026-09-11 (final) — board closed out at 7 open items

Two open actions from the Sep-11 call were living inside tile notes rather than
being tracked as decisions. Both have an owner and neither has an answer, which
is exactly what the decisions list is for:

- **Where the dollar value of all inventory comes from.** The *meaning* of
  "Inventory Balance" is now settled; the source is not. Jennilyn is asking
  Justin. Same underlying blocker as the part-cost question — if Plex costing
  gets populated, both resolve at once.
- **The Monday holding board does not exist yet.** Everything on our side of
  the Label Design queue is built. Monday's column IDs are per-board and are
  not the column titles, so the push cannot be finished by guessing them.

The board now links to the Field Manual for how each tile is built, so the two
artifacts have one job each: **status** on the board, **understanding** in the
manual.

## 2026-09-11 (docs) — study material, and Plex's glossary made usable

### Added — `scripts/distill_glossary.py` and `docs/PLEX_GLOSSARY.md`
Plex's glossary export is **61,022 entries / 6.4 MB**. Reading it is not the
problem; carrying it is. The script reads it once, locally, and keeps only the
terms matching vocabulary found in `reports/` — **93 of them**, 12 KB.

Matching normalises case and underscores so `Minimum_Inventory_Quantity` finds
Plex's "Minimum Inventory Quantity", and deliberately does **not**
substring-match: a first pass that also scanned `catalog/` pulled in ~1,000
fields from HR and claims modules nobody here touches, which is exactly the
problem the script exists to solve.

Two findings worth more than the definitions:

- **Plex defines none of the 100 views we extract.** Its glossary covers
  business terms, not database views. When one comes up in a meeting there is
  no authority to appeal to — the answer comes from the data or from Vox.
- **A missing field is either undefined by Plex or named by us.** Worth
  knowing before saying "Plex calls it that".

### Added — the Scorecard Field Manual
A study artifact: all 22 tile families taken apart into *what question it
answers*, *which Plex tables it comes from*, *why it is built that way*, and
*what might not be true*. Plus the vocabulary traps that have each cost real
time here (Encapsulating vs "Encapsulation", Scrap vs Destroy, Part vs
Warehouse, status names vs keys), a consolidated list of every assumption and
placeholder currently in production, and the distilled glossary with search.

Written for the case where someone asks *"where is that used?"* or *"why do we
need that at all?"* — questions the existing docs answer only by implication,
scattered across a changelog and a dozen report files.

### Changed — README and CHEATSHEET
The README now opens with where to learn this project rather than assuming the
reader already knows. The cheatsheet gains the glossary workflow and the two
mistakes that have cost the most time: look under `Part` before believing Plex
cannot do something, and filter on status **names**, never numeric keys.

## 2026-09-11 (deployed) — Out of Stock fired for the first time

Credentials refreshed, so everything queued up today actually ran.

### Verified — `inventory_out_of_stock_report` returned FOUR rows
The tile has been empty for its entire life. At 16:40 it held four real
shortages — `33102-00VOXNU-0` short **2,964,559** against a 2,086,325 minimum,
`33125-00VOXNU-0` short **12,002,000**, `33147-00VOXNU-0` short **4,527,800**,
`33190-00VOXNU-0` short **20,877,000**. Real minimums, real BOM-exploded demand,
end to end.

**An hour later it read 0 again, and that is the view being right rather than
flaky.** The minimums are still set; demand on those parts fell to zero because
orders moved into **Quote** status in Plex between the two reads. Demand counts
only what Plex flags `Include_In_MRP` — Pending Fulfillment and Hold — so a
quote is correctly not demand. The same event is visible from the other side:
quote lines in `pipeline_plex_value_report` jumped **3 → 35** over that hour.

Recorded here because the four-row reading is now the only evidence that exists
— the tenant has already moved on, and "it has never returned a row" would
otherwise still be the story.

### Deployed — `part_cycle_count_report`
Created and answering. Returns 0 rows because nothing has been cycle counted on
the test tenant; `raw_Part_v_Cycle_Inventory` is empty too, so this is an
upstream absence rather than a broken view — exactly the distinction the
`-Quality` switch was added to make. Counting is lumpy by design, so an empty
month is expected.

### Ran — sales_orders, part_on_hand, work_orders, quality, inventory_snapshot
All test. Views verified directly, not trusted from exit codes. Now carrying
data that was empty this morning: **Open Bottles** (3 open jobs), **Open Caps**
(4), **pipeline** (35 quote lines), **Quantity Available** (112 parts).

**The first real Quality deviation landed** — one record with its part linked,
ahead of Sheldon's Thursday session.

**Every revenue view reads 0 together**, which is the signature of a tenant with
no shipments rather than of a view problem.

### Fixed — `scorecard_status.ps1` could not run at all
Written as UTF-8 **without** a BOM, and PowerShell 5.1 reads `.ps1` as ANSI, so
every em-dash became mojibake and the parse failed on the first string. Re-saved
as UTF-8 with BOM.

Worth recording because the syntax check that was supposed to catch this
**reported success without checking anything**: the `[ref]$e` in it errored
before `ParseFile` ever ran, and the `else` branch printed "PS1 parses OK".
A validation step that cannot fail is worse than none.

### Still blocked
`terraform apply` — the local permission classifier stops it, so it needs a
human. Pending in it: the `part_cycle_count_view.sql` GCS object (the file is in
the bucket via `gcloud storage cp`, but Terraform's state does not know), and
the whole `label_design` job, which has configs and SQL but **no Cloud Run job
or scheduler resources yet**. `label_design_report` is the one view still
MISSING, and it cannot be created until that job exists.

## 2026-09-11 (night) — Label Design notifications, and getting ready for Quality

### Added — `deploy/label_design_sync/`
The Apps Script half of the Label Design queue: reads `label_design_report`,
decides which rows are new, writes them to the sheet and pushes them to the
Monday holding board.

**The notifications live here, not in the pipeline**, and that placement is the
point: the Cloud Run job knows a query succeeded; only this knows what reached
Monday.

| When | Who | What |
|---|---|---|
| Every run (10:00, 14:00) | Emilio, marketing@ | Counts, the new rows, any problems |
| Nightly (18:00) | Ashley, Kelli, Jennilyn | One digest |

**The "errors only" filter was dropped on request, and it was the right call.**
A silent success and a job that never fired look identical from outside, and
the reason this was automated is that nobody notices when a manual step stops
happening. The nightly summary therefore treats **no sync ran at all** as its
own loud case, separate from "problems occurred" and from "nothing new today"
— the last being normal, and said plainly so a quiet day doesn't read as a
broken one.

**Dedupe is order number + customer part number against BOTH tabs.** The
`historical` tab is read and never written, because notes and reason codes are
hand-edited there and re-writing a row would overwrite that work. If either tab
lacks those columns the run **stops** rather than continuing — without them
nothing can be deduplicated, and the failure mode is writing the whole queue
again.

Two Monday-specific traps handled: items are created **one at a time** (a batch
failing halfway leaves the sheet written with no way to tell which half landed),
and the API answers **`200` with an `errors` array** rather than an HTTP error,
so the status code alone would report success on a rejected mutation.

A failed push deliberately does **not** undo the sheet write: the row stays, the
key is recorded, and the next run won't repeat it. "On the sheet, not on the
board" is a state the email names, and fixing it is a manual re-push rather than
a re-run.

**Not finished:** the Monday column IDs in `pushToMonday_` are placeholders
until the holding board exists — they are per-board and are not the column
titles.

### Fixed — `scorecard_status.ps1` was already out of date
It shipped this morning without `label_design_report`, which did not exist yet
when it was written. Added, under a new Operational group.

### Added — `-Quality` switch, for Thursday
Sheldon is creating destruction, deviation and rework records this week, and
**the test tenant resets**, so the evidence has to be inspected the same day it
is made. The switch counts the **raw** Quality tables alongside the views,
because a view returning 0 rows cannot distinguish the two failures that matter
that day:

- **raw table has rows, view has none** → the view is wrong, and that is ours
  to fix while the data still exists.
- **both empty** → the record never left Plex; check the extraction ran at all.

Without the raw counts, both look like "the report is broken" and a day of
someone else's test data gets wasted on the wrong diagnosis.

## 2026-09-11 (evening) — the Sep-11 meeting, and one artifact instead of two

### Added — `label_design` pipeline, replacing a twice-daily manual loop
Jennilyn's Plex stored procedure `sproc338756_18319605_1407579` ("Label Design
Report"), rebuilt as `reports/label_design.yaml` + `label_design_view.sql`
(both configs, 10 extractions each). It replaces: download from NetSuite, paste
into a sheet, check duplicates by hand, upload to Monday.

**The three additions asked for on the call:**
- **The outside sales rep / BDM name**, so a designer with a question knows who
  to ask. **Not guessed at** — Plex holds a primary and a secondary rep and
  which one Vox calls the BDM has never been stated, so *both* ship and the
  consumer picks.
- **Order status = Pending Fulfillment.** The procedure filtered only the
  *release* status being Label Design, so it also returned lines on orders
  nobody had approved.
- **A 14-day rolling window** on the order date.

Matched on the status **name**, not the key — the vanished-key failure that
killed the accounting-approval report is the reason.

**Dedupe is order number + customer part number**, her rule, and it lives in
the Apps Script rather than the view: dates change and an order can be
cancelled and reopened, while the same customer part on a *different* order
legitimately repeats. Three tables were new to the repo
(`Sales_v_Release_Status`, `Sales_v_PO_Line_Note`, `Part_v_Customer_Part`).

Seven tables are extracted here **again** despite `sales_orders` owning them:
this runs at 10:00 and 14:00, hours after that pipeline ran overnight, and a
label-design queue built on a 14-hour-old order list would miss exactly the new
orders it exists to surface.

Still to build: the Apps Script on the duplicate sheet, and the push to the
Monday holding board.

### Fixed — cycle-count accuracy was the wrong kind of average
The view computed accuracy **weighted by quantity**, reasoning that averaging
per-count percentages lets a one-container location count the same as a full
rack. That is defensible arithmetic and it is **not what Vox means**.

Their definition: each assigned location is judged accurate or not — it held
what it was supposed to or it didn't — and those yes/nos are averaged. A
per-location hit rate, deliberately blind to how much sat in each location.
Corrected, with the quantity-weighted figure kept beside it as
`accuracy_pct_qty_weighted`, because the two diverging means the misses are
concentrated in the big locations.

Also regrouped to one row per **month** rather than per location per month,
matching the three numbers the warehouse actually tracks: locations counted,
items counted, accuracy. Counting is lumpy by design, so `locations_counted`
must be checked before showing a percentage — an empty month would otherwise
read as 0% accurate.

### Answered — six decisions closed in one meeting
- **Deposit Review IS the accounting approval**, and the chain is on record:
  Quote and Pending Sales Approval are internal *sales* stages; Deposit Review
  is the accounting review; a payment applied moves the order to Pending
  Fulfillment. Repointing was right.
- **The field is `Minimum_Inventory_Quantity`** — not "minimum stock level",
  which is the phrase everyone says and no field is named. The `33` parts exist
  only in test, but **plenty of `12` parts already carry real minimums**, so the
  Out of Stock wiring is testable today rather than blocked on data entry.
- **Cutover is 19 October**, with the pre-Plex source used through the 16th.
  Fallback if the Plex figure doesn't arrive: payments are applied in NetSuite,
  so the same number can still be pulled from there post-cutover.
- **Cycle count is in scope**, with its three metrics defined (above).
- **The TAT standards were never missing.** They sit in a table on the Monthly
  TAT Analysis sheet, keyed by Item Stock Type, in days — agreed they move into
  the manual-data app, *with restricted edit access*.
- **"Inventory Balance" is the dollar value of all inventory**, raw materials
  through finished goods. Definition settled; source is not — Jennilyn is
  asking Justin, most likely a costing report.

### Added — three decisions nobody had put to anyone
- **The TAT clock start** (`Problem_Date` vs `Entered_Date`), decided in code
  and flagged only in the SQL. Now that the standards are known to exist, this
  matters: if they were set against Entered Date, our figure runs consistently
  larger and will look like performance dropped on cutover day.
- **DPMO's `Opportunities_Per_Unit = 1`** placeholder, feeding the second
  heaviest-used source on the scorecard.
- **Who may edit the manual-data form.** Raised about the TAT standards and
  then broadened to all of it. The app is currently open to anyone in Parasol
  Group Inc — right for a daily activity log, wrong for bonus-bearing
  standards.

### Changed — one board, not two
The sign-off artifact **should not have been created**: it and the Migration
Board tracked the same work from two directions, so a question could be
answered in one and still look open in the other. Decisions now live on the
Migration Board next to the tiles they block, and the sign-off URL is a
retirement notice pointing at it. Both links still resolve; neither was
recreated.

Also closed there: **deviation and destruction test data has an owner and a
date** — Sheldon from Quality, session on Thursday. The tenant resets, so the
data has to be inspected the same day it is made.

## 2026-09-11 (last) — a repeatable way to prove the scorecard has data

### Added — `scripts/scorecard_status.ps1` and `docs/SCORECARD_DATA_LOAD.md`
Preparing the scorecard for a demo kept meaning "run things and hope". The
script checks all **31 views the scorecard reads** in one pass and reports each
as one of three states that look identical on a dashboard tile and mean
completely different things:

- **`MISSING`** — the view was never created. This is the one to act on, and
  it is invisible to the thing people check: a `gcloud run jobs execute --wait`
  exits 0 even when view creation failed, because the extractions succeeded.
- **`0 rows`** — the view exists and the Plex tenant simply has nothing of that
  kind. Almost always Vox's side, not ours.
- **`n rows`** — real data.

The runbook orders the pipeline runs by a dependency that is easy to get wrong:
**`sales_orders` owns `raw_Part_v_Part`**, which the inventory, parts and work-
order pipelines read rather than re-extracting, so it has to run first.

It also states plainly which tiles **cannot** be filled from this side —
production, quality, inventory valuation and Out of Stock are all waiting on
data entry or costing in the Plex test tenant, not on a deploy. Writing that
down is the point: it stops a demo being spent debugging an empty tile that was
never ours to fill.

### Added — Terraform resource for `part_cycle_count_view.sql`
The new view's SQL had no `google_storage_bucket_object`, so it would never
have reached GCS and the view would have failed to create with a missing-file
error on the next run. `terraform validate` passes.

### Blocked — the data load itself
`bq` and `gcloud` fail with *"Reauthentication failed. cannot prompt during
non-interactive execution"* despite `gcloud auth list` showing an active
account — the org policy documented in `CLAUDE.md`. **Needs `gcloud auth login`
in an interactive terminal**, along with `terraform apply`, which this
machine's permission classifier blocks. Everything up to that point is
prepared and validated.

## 2026-09-11 (later) — six sign-off items closed, and two nobody had asked

### Added — company-wide goals and month frontloading
- **Company-wide is now a scope on every metric, not just revenue.** `(company-wide)`
  sits at the top of the rep and work-centre-group lists and stores a **blank**
  scope, which is what the reports emit. **Production had no way in at all**
  before this, so the production tile could only ever be compared against
  per-group targets that may not exist.
- **One entry fills a run of months.** Goals are set once at the start of a
  year and changed occasionally, so entering twelve one at a time was the
  common case. Each month is written as **its own row**, so a later edit to one
  month leaves the rest alone; capped at 24 so a typo can't write years of rows.
- `repeat_months` is a **transient** field — it shapes what gets written and is
  not itself a column. `allFields_()` excludes transient fields from both the
  sheet and the table.

### Added — cycle count extracted, not just catalogued
`Part_v_Cycle_Inventory` and `Part_v_Cycle_Frequency` now extract on the
`part_on_hand_inventory` pipeline (**both configs**, 4 extractions each), with
`part_cycle_count_report` reporting accuracy and coverage per location per
month.

- **Accuracy is reported twice on purpose.** Plex's own `Accuracy` column is
  per-count and can't be averaged into a period figure without weighting, so
  `accuracy_pct` is recomputed from accounted-for / unaccounted-for quantities
  and `avg_plex_accuracy` sits beside it — a disagreement surfaces rather than
  one quietly standing in for the other.
- `no_quantity_counted` is explicit, because a month where nothing was counted
  would otherwise read as **100% accurate**.
- `Part_v_Cycle_Frequency` is extracted but **not yet joined** — the join key
  is unconfirmed until there are real rows, and extracting it now means review
  needs no second deploy.

### Fixed — the part-cost question was the wrong question
`Product_Cost` being unusable was treated as "we have no cost source". Wrong:
**Plex costs parts itself** through `Part_v_Snapshot`, and
`inventory_valuation_summary_report` is already built on it — it returns 0 rows
because **nothing has been costed on this tenant**, not because the source is
missing. That turns an open-ended sourcing question into a Plex operations one,
and unblocks three tiles at once whenever costing runs: Deviation $, Inventory
Balance, Rework $.

### Fixed — two placeholders that had never been put to the business
Re-reading `VOX_SCORECARD_PLEX_MIGRATION_MAP.md` surfaced two numbers decided
in code and flagged only in a file nobody outside this repo reads:

- **DPMO's `Opportunities_Per_Unit = 1`** — with 1, DPMO and defect rate are
  the same number wearing different labels. Feeds YTD FPY, the second
  heaviest-used source on the scorecard (9 charts).
- **The TAT clock starts at `Problem_Date`, not `Entered_Date`** — the gap is
  reporting lag, and if the existing standards were measured from Entered Date
  our figure runs consistently larger and will look like performance dropped on
  cutover day.

Both are now on the sign-off board as questions rather than as SQL comments.

### Changed — "Inventory Balance" and the TAT standards stopped being mysteries
- **Inventory Balance** sits on the `Rev_MTD` source beside MTD Revenue,
  Revenue in Shipping and Revenue in WIP — all dollar values. Read with the
  Sep-9 on-hand definition, a valued inventory balance is the only reading that
  fits, which makes it a yes/no rather than "nobody knows what this is".
- **The TAT standards already exist.** Both TAT tiles are fed by sheets
  carrying `Item Stock Type` / `Performance Standard` / `Bonus Standard` /
  `Average Work Days`. The ask changed from "dictate the standards to us" to
  "share the sheet" — access beats a dictated list, and can't be typed wrong.

### Changed — sign-off board v10
Down to **6 open from 10**. Four closed on the Sep-9 answers (revenue target,
production goals, minimum stock levels, deviation test data), two by building
rather than asking (cycle count, pre-Plex history parked). Every remaining item
names the **tile** it blocks.

**One correction worth recording:** the call's *"on question two, it's no"* was
answering the **demand** question, not "Orders Pending Approval by Accounting".
Reading it as the latter would have repointed a live report on an answer that
was never given, so that item stays open — with Deposit Review named as the
leading candidate and the reasoning shown.

## 2026-09-11 — one app for every manual number, with the sheet back in the middle

### Changed — `deploy/goals_web_app/` → `deploy/manual_data_app/`
The goals app covered **one** of the manual inputs the Sep-9 call actually
named. Re-read against the transcript, the ask was broader: *record an
incident*, production goals, rep sales goals — and the sign-off board adds
turnaround standards and (conditionally) part costs. Rebuilt as **one app with
a dataset registry** rather than four near-identical forms.

- **Adding a manual dataset is now a registry entry plus `setupSheets()`** —
  no new form code. `Index.html` generates itself from the registry; if adding
  a dataset needs an edit there, the registry is missing a field type.
- **Four datasets ship:** `goals` → `scorecard_goals_app` (unchanged contract,
  so `v2_scorecard_goals_resolved` and the three `v2_*_vs_goal` views keep
  working untouched), `incidents` → `safety_incidents`, `turnaround_standards`,
  `part_costs` → `part_cost_manual`. The last is gated on sign-off item 04 and
  is inert until something reads it.
- The old directory is **deleted, not deprecated** — it was never deployed, so
  there is nothing to migrate and leaving it would give two plausible apps to
  paste into Apps Script.

### Fixed — the script's Cloud project is not the data's Cloud project
`GCP_PROJECT` was doing two jobs: naming the project that runs the BigQuery
jobs *and* qualifying every table reference. The Apps Script project lives in
**`parasoldatalake`** while the data lake is **`voxdatalake`**, so every query
would have gone looking for `parasoldatalake.PlexTest.*` — a not-found error
that reads like a missing view rather than a misrouted project.

Split into `GCP_PROJECT` (runs and bills the jobs) and a new optional
`BQ_DATA_PROJECT` (where the tables are), the latter defaulting to the former
so a single-project setup needs no extra property. The load job now writes to
the data project while still running in the script's own.

### Fixed — a fresh deployment now explains itself
The first real deploy hit `Could not load: ScriptError: Script property
GCP_PROJECT is not set`, which is accurate and tells you nothing about where to
go. `getFormData()` now returns unset properties as a **state** rather than
throwing, and the form renders a setup panel naming each missing property, its
value, and whether the BigQuery advanced service is enabled — both are editor
settings rather than code, so a new project always needs them once. It also
says that properties are read per request, so fixing them needs a **reload**
rather than a new deployment version.

### Changed — the sheet is back, as a log nobody types into
`web app → Google Sheet (one tab per dataset) → BigQuery`, replacing the
previous direct `tabledata.insertAll`.

- **The sheet is the record of truth**; the BigQuery table is a mirror that
  `pushAll()` rebuilds from it. It survives a dropped table or a test→prod
  dataset swap, and it is readable by someone with no BigQuery access.
- **Nobody types into it** — the app is the only writer, and each tab says so
  in its header row. That keeps the break-the-sheet failure mode away while
  still getting a human-readable log.
- **The push is a load job, not a streaming insert**, which removes the one
  piece of user-visible weirdness the old design had to document: a saved row
  is queryable *immediately* instead of sitting in a streaming buffer for a
  few seconds looking like it hadn't worked.
- **A failed push does not fail the save.** The row is in the sheet; the form
  says the push lagged, and an hourly `pushAll()` trigger repairs it. Losing
  what someone typed for a reason unrelated to them is the worse outcome.
- **The load job is waited on** (`waitForJob_`). A load job is asynchronous —
  without this a failure is invisible and the form reports success for a push
  that never happened.
- Tabs stay **append-only**, so `WRITE_TRUNCATE` carries the full history
  across on every push and the newest-row-per-key semantics are unchanged.

### Changed — sign-off board rewritten so every item is answerable
`reference_vox_signoff_board` artifact, v8. Several items were addressed to
the data rather than to Jennilyn — *"what does `Product_Cost.part` key to?"*
is a question for whoever owns that table, and she could not have closed it.

- Every item is now **pick an option, name a person, confirm a date, or supply
  a number**, grouped by which.
- **Each carries a stated default** (*"if we don't hear"*), so silence closes
  an item instead of parking it — which is what makes the list clearable in
  one meeting.
- The three genuinely blocked on Plex data entry are grouped under a heading
  that admits they can't be defaulted, so it is obvious those are the only
  real carry-over.
- Options trimmed where a third was a variant rather than a real branch
  (revenue target, accounting status, production goals); kept where the
  branches are genuinely different (cost source, cycle count metric).

### Removed — transcript quotes from anything that gets pasted into Apps Script
`Code.gs` / `README.md` quoted the Sep-9 call verbatim with attribution. Those
files are pasted into a project Jennilyn may be added to, the way she added us
to hers. The reasoning is kept; the quotes and names are gone. The full
transcript record stays in `meetings-reference/` and `CHANGELOG.md`, which
don't leave the repo.

## 2026-09-09 (last) — three open questions closed from data

None of these needed a meeting. Each was answered by querying something.

### Answered — where destructions are logged. Plex calls it `Scrap`.
- Jennilyn's open question: *"destructions is like a disposition, but I'm not
  sure where we would find that... I actually need to ask because I'm not sure
  where they note that they destroyed something."*
- Extracted **`Quality_v_Final_Disposition`**, **`Quality_v_Initial_Disposition`**
  and **`Quality_v_Disposition_Type`** and read the value lists in full:

  | List | Values |
  |---|---|
  | `Final_Disposition` | *(blank)* · Re-introduce · Return · Rework · **Scrap** · Use as is |
  | `Initial_Disposition` | *(blank)* · Hold · Return · Rework · Scrap · Sort & Rework · Sort & Scrap · Use as is |

- **There is no "Destroy" value. Plex calls destruction `Scrap`** — which is
  why searching for a destruction field found nothing. Destroyed material is a
  nonconformance record whose **final** disposition is `Scrap`.
  `Quality_v_Disposition_Type` came back with **0 rows**, so the other
  candidate home for the concept is eliminated rather than left open.
- **New `quality_disposition_cost_report`** groups nonconformance cost and
  quantity by what was *done* with the material rather than by problem
  category. Destruction $ is now a filter (`disposition_class = 'Destruction'`).
  0 rows today because the quality tables are empty — but the value lists are
  real, which is what made this answerable now.
- **⚠ Rework deliberately NOT settled.** It exists both as a disposition here
  and as a container inventory status, and Jennilyn named the **container**
  one: *"rework should have the inventory status of rework."* Those are
  different populations that will not agree. This report exposes the
  disposition view; the container-status version is not built, because it
  needs a per-container cost. Documented rather than silently picked.
- The dollar figure is Plex's own `Quality_v_Problem.Cost`, so it needs no
  external cost table — but it may be patchy, so **`records_missing_cost`**
  ships beside it rather than letting a half-populated total read as a small
  number.

### Answered — revenue goals existed all along, as the company-wide sales goal
- **All 12 monthly revenue goals loaded**, and `v2_revenue_vs_goal_report` now
  returns a real goal and variance (Sept: **$65 actual against $5,040,000**)
  while the untouched original still returns `NULL` — the migration seam
  working exactly as designed.
- **Loaded into `scorecard_goals_app`, not `scorecard_goals`.** The latter is
  replaced `WRITE_TRUNCATE` on every spreadsheet push, so a hand-loaded row
  there would vanish the next time somebody saved the sheet. This is what the
  append-only override layer is for.
- **⚠ It rests on a stated assumption.** The figures are copied from the
  **company-wide sales goal**, the only company-wide monthly target that
  exists anywhere in BigQuery — it was hardcoded as a 12-row `UNION ALL`
  inside `VoxScorecardsLive.vw_sales_mtd_vs_goal`, which measures it against
  `vw_sales.amount` by `date_approved`, i.e. **ordered, not shipped.** Revenue
  and Sales are deliberately different metrics here, so using one target for
  both is a business call, not an equivalence the data proves. Every loaded
  row carries a `note` saying so, and retracting them is one tombstone away.
- Confirmed there is **no revenue-goal or production-goal table** anywhere in
  `VoxScorecardsLive` (all 39 tables and views listed), which matches
  Jennilyn's *"revenue goals exist and we could frontload... the production
  ones usually don't."*

### Answered — cycle counting is under Part, not Warehouse
- `reports-list/warehouse.md` and `catalog/plex_warehouse_views_catalog.md`
  had `Warehouse_v_Cycle_Count` / `_Line` marked ❓ estimated-only. They are
  now **confirmed absent** — the ODBC driver returns "Base table … not found".
- But cycle counting is alive under the **Part** module:
  **`Part_v_Cycle_Inventory`** (`Location`, `Accuracy`, `Accounted_For`,
  `Moved`, `Unaccounted_For`, `Cycle_Inventory_Date`, `Cycle_Inventory_By`,
  `Accuracy_Quantity`), plus `Part_v_Cycle_Count_Type`,
  `Part_v_Cycle_Frequency` (`Accuracy_Threshold`) and
  `Part_v_Container.Cycle_Inventory_Status`.
- **The same Part-not-Warehouse trap as on-hand inventory**, where
  `Warehouse_v_Part_Quantity` was the intuitive guess and `Part_v_Container`
  was the real carrier. Now in `docs/CHEATSHEET.md` as a general rule: when a
  warehouse-shaped concept comes back missing, look under Part before
  concluding Plex can't do it.
- Cycle Count moves from 🔍 *candidate* to 🎯 *buildable, awaiting a scope
  decision*. Nothing is extracted yet and row counts are unknown.

### Fixed — a cost source that looks right and is not
- **`VoxScorecardsLive.Product_Cost` is not usable**, and it is the obvious
  thing to reach for whenever a report needs a part cost and Plex's cost
  tables are empty. Tested: 199 rows of `part` + `cost_ea` joining to **5 of
  6,221** Plex parts and **none** of the `33` parts. Its `part` values are
  bare stems (`12335`) against Plex's full numbers (`12335-01VOXNU-1`), and it
  contains duplicate rows. Even stem-matching fails almost everywhere.
- Recorded in `docs/CHEATSHEET.md` and on
  `inventory_valuation_total_report.md`, because this nearly went the other
  way: it was about to be reported as unblocking deviation value and Rework $,
  and only the join test caught it. **Ask what its `part` column keys to
  before building on it.**
- Consequence: **deviation value and container-based Rework $ are still
  blocked** on a cost source, but the question is now specific rather than
  open-ended.

## 2026-09-09 (later still) — two goal sources, side by side

Goals can now be edited in a **web app** instead of a spreadsheet, without
cutting over: both sources run in parallel and the scorecard picks per goal.

### Added — `scorecard_goals_app` and `v2_scorecard_goals_resolved`
- **A second goal table**, `scorecard_goals_app`, created by hand in
  `PlexTest` and `PlexProd`. Same columns as `scorecard_goals` plus
  `is_deleted`. **Append-only**: every save inserts a row and the newest per
  `(metric, period_month, scope)` wins, so two people editing the same goal
  minutes apart cannot lose each other's write, and every edit stays as
  history.
- **`v2_scorecard_goals_resolved`** is the seam: **app first, sheet as
  fallback.** A goal entered in the form wins; a goal absent there falls
  through to the spreadsheet, so nothing goes blank mid-migration.
- **Deleting is a tombstone, not a delete.** `is_deleted = TRUE` means "the
  app has nothing to say about this key", which restores the *spreadsheet*
  value rather than blanking the tile — the only sensible reading while both
  sources are live.
- Exposes **`goal_source`** (`app` / `sheet`) so it is always visible which
  source fed a given goal.

### Added — `v2_*_vs_goal` views, generated rather than copied
- `v2_revenue_vs_goal_report`, `v2_sales_vs_goal_report` and
  `v2_production_vs_goal_report` are **generated** by
  `scripts/gen_v2_goal_views.py` from the three originals, with the single
  goal-source `FROM` swapped to the resolver. Edit the original and re-run
  the generator; never hand-edit them.
- **The originals stay deployed and unchanged**, so Looker Studio migrates
  **one tile at a time** rather than in a cutover. Verified: each v2 view
  returns *exactly* what its original returns while the app table is empty
  (sales 69 = 69, production 2 = 2, revenue 1 row) — so adopting them changes
  nothing until someone uses the form.
- The generator **refuses to run** if an original stops referencing the goal
  table exactly once, rather than silently producing a wrong copy. It caught
  the revenue view naming the table in a header comment on the first run.
- `goal_source` is deliberately **not** surfaced on the v2 report views —
  that keeps each generated file a minimal diff from its original. Query the
  resolver directly to see provenance.
- The resolver is listed in **both** the sales_orders and work_orders configs
  on purpose: goal views live in both pipelines and each must be able to
  create its own dependency without waiting on the other's run. The SQL is
  identical, so whichever runs second replaces an identical view.

### Added — `deploy/goals_web_app/`
An Apps Script web app (`Code.gs` + `Index.html` + README), modelled on
Jennilyn's existing sales-KPI form. *"I don't want to do it in a sheet
because people tend to break the Google Sheets all the time."*

- **Scope dropdowns are read from the reports, never typed.** `scope` is an
  exact string join, so a typo produces a NULL goal that reads as 0% forever
  with no error — the live example being Plex's `Encapsulating` against the
  tile's "Encapsulation". Options come from `sales_mtd_summary_report` and
  `production_monthly_by_workcenter_group_report`, which makes that class of
  mistake impossible.
- **Shows the running sum of rep goals against the company-wide target as you
  type** — Emilio's ask on the call. The two are allowed to differ (turnover;
  $5,040,000 team vs $4,690,000 across eight reps), so it reports the gap
  rather than blocking on it.
- Enforces the month being the **1st** (reports group by month, so a
  mid-month goal would form its own bucket and never match), rejects negative
  and non-numeric values, and stores company-wide as a blank scope to match
  what the reports emit.
- Writes via `tabledata.insertAll` rather than DML, because BigQuery limits
  concurrent DML on a table and a shared form can hit it. The cost is a few
  seconds before a saved row is queryable — documented, with a warning not to
  save twice.
- `skipInvalidRows: false` on purpose: schema drift should fail loudly rather
  than quietly write a goal no report will match.
- The README carries the trap that bit Jennilyn: **saving Apps Script code
  does not update a live web app** — it needs a new version deployed, and the
  URL can change.

### Verified
Precedence and fallback tested against the 68 real goal rows on `PlexTest`:
an app row for a key the sheet already had flipped that key to `app` **with
the row count unchanged at 68** (the override displaced its twin rather than
duplicating it), and a tombstone for the same key fell back to the sheet's
**60,000** exactly. Test rows removed; the app table is empty until the form
is used.

**Not yet in `PlexProd`** — the four views arrive there on tonight's
scheduled production run. Not forced manually, since a prod run emails the
team.

### Sunset plan
When the spreadsheet ETL goes: delete the three original views, drop the
`v2_` prefix, delete the `sheet` branch from the resolver (it becomes a thin
read of the app table), and delete the generator. No consumer of the `v2_`
views has to change.

## 2026-09-09 (later) — the Sep-9 meeting

`meetings-reference/sep-9/`. Four open questions answered, and Jennilyn fixed
one of them **in Plex** rather than in our SQL, which changed live numbers.

### Changed — WIP is Pending Fulfillment + Hold. The broad/strict ambiguity is closed.
- Open since 2026-09-04, when she had defined WIP two incompatible ways in one
  conversation. Her ruling: *"really, it should just be pending fulfillment. I
  guess hold as well would be WIP because it was sold but it hasn't shipped
  yet. So it just be those two statuses"*, and *"we don't want to count
  pending sales approval because that's not considered an order yet."*
- The old filter was "not a quote, not cancelled", which under Vox's status set
  also swept in **Pending Sales Approval, Deposit Review and Closed**.
  **WIP fell from $43,723 to $17,950** once corrected — the old figure was
  inflated by roughly 2.4x.
- Also nets `Quantity_Shipped` off the release, per *"if partials have
  shipped, we only want the WIP as the value of all of the order lines that
  haven't shipped yet."*
- **The Pipeline double-count is eliminated, not just measured.** Quote and
  Pending Sales Approval can no longer appear in WIP at all, so
  `also_counts_in_pipeline` is now a hardcoded FALSE (kept by name for
  downstream consumers) and `is_on_hold` replaces it as a real flag.

### Changed — demand now excludes unapproved orders, because Plex says so
- *"I did change it in Plex because I saw that it was showing demand for
  deposit review and pending sales approval. We don't count those as demand
  until they're pending fulfillment."* Confirmed live the same day:
  **`Include_In_MRP` is now 1 on exactly Pending Fulfillment and Hold**, and 0
  on Quote, Pending Sales Approval, Deposit Review, Closed and Cancelled.
- **This needed no code change**, because the demand gate was already Plex's
  own flag rather than a hardcoded status list. Order demand in
  `inventory_available_to_sell_report` dropped from **508,807 units to 5,000**
  on its own. That design choice paid for itself within a day.
- **The `_firm_` columns are deleted rather than kept.** Their definition
  (`Hold = 0`) would now wrongly drop the `Hold` status she explicitly wants
  counted, and a stale second reading is worse than none. Availability is down
  from four columns to two — `available_vs_orders` and
  `available_vs_total_demand` — the only remaining choice being whether
  BOM-exploded demand counts, which for `33` parts it must.
  `order_demand_from_held_orders_qty` keeps the Hold portion visible.

### Fixed — a report had been silently dead, and nobody could have noticed
- **Vox cut the sales-order status list from 10 to 7** in the same pass:
  **Pending Payment Review (2638), Pending Shipment (2639) and Quote Lost
  (2655) no longer exist.**
- `sales_orders_pending_accounting_approval_view.sql` filtered
  `PO_Status_Key = 2638`. It returned 0 rows and would have returned 0 rows
  forever, reading as "no orders pending approval" rather than "this filter
  can never match". A repo-wide sweep for the three dead keys found this as
  the only view filtering on one (the other hits were comments).
- Repointed to **Deposit Review**, matched on the status **name rather than
  the key** — a vanished key is what broke it. **It now returns 2 real rows.**
  This is the second inference about what "by Accounting" means, and the first
  was already flagged unconfirmed, so it still needs Jennilyn; the `status`
  column is in the output so a reader can see what produced each row.

### Confirmed — decisions that needed no code change
- **The `33` part rule stays name-based.** *"The 33 is the most reliable
  way"* — she explicitly rejected switching to a part-type dropdown because it
  would break the rule. Worth recording, since scanning a part number looks
  like the fragile choice and isn't.
- **Container statuses: exclude rework, lab analysis, defective and expired.**
  *"Once the container is reworked, it won't be in a rework status anymore. And
  at that point it will be inventory."* The current on-hand list (OK, Hold,
  Inspection Required, Hold for Design Order) already does exactly this, so
  the open question closes with no change — and the earlier suggestion to
  *include* Rework as available supply was **rejected**.
- **The goal discrepancy is accepted, not a bug to fix.** *"We'll have both.
  So we'll have the total month goal like for the team and then we'll have
  their individual goals... even if their individual goals don't add up to this
  goal, we're just going to sum everything for the team."* The
  $5,040,000-vs-$4,690,000 gap is by design, caused by rep turnover.
- **Revenue goals exist and can be front-loaded; production goals usually
  don't exist.**

### Still open after this meeting
- **Where destructions are logged.** *"I'm actually not totally sure...
  I actually need to ask because I'm not sure where they note that they
  destroyed something."* Assigned to Jennilyn.
- **Deviation value** = pieces affected x part value, dated by effective
  date — but *"I need them to test this more"* before building.
- **Rework $ should come from the container `Rework` inventory status**, not
  the quality nonconformance category. Not built: the quantity is reachable
  today, the dollar value needs a cost source, and inventory valuation is
  still empty.

## 2026-09-09

### Added — `inventory_available_to_sell_report`, and the real reason OOS was empty
Jennilyn asked directly (email, 2026-09-04) where to see **Quantity
Available**: *"Traditionally, we use Quantity on Hand − Quantity (Sold,
Demand, Allocated, etc)."* Amber answered with two Plex screens, and the
screenshots of them settled a question this repo had been guessing at for
weeks.

- **`Sales_v_Release_Allocation` was never going to work, and that is why
  `inventory_out_of_stock_report` returned 0 rows for its entire life**
  against a count of 5 on Jennilyn's own sheet. It has 0 rows in `PlexTest`
  and `PlexProd` and always has. Allocation is a **picking/staging** concept
  — which container is committed to which shipment — not demand. The docs
  had been recording this as "genuinely empty upstream," which is true and
  entirely beside the point.
- **Demand lives on sales-order releases.** Plex's own "Sales Order Line
  Inventory Check" screen splits it into **Orders** (the part is on an order
  line), **Order Reqd** (a parent finished good is on order and this part is
  a component) and **Job Reqd**. `Sales_v_Release` — already extracted —
  carries `Quantity`, `Order_Quantity` and `Quantity_Shipped`. Note
  `Sales_v_PO_Line` has **no quantity column at all**; the quantity is on the
  release.
- **Which statuses count as demand is now Plex's answer, not ours:**
  `Sales_v_PO_Status.Include_In_MRP`. Read live across all 10 statuses — it
  is 1 on Pending Sales Approval, Deposit Review, Pending Fulfillment,
  Pending Payment Review, Pending Shipment and Hold, and 0 on Quote, Quote
  Lost, Closed and Cancelled. So quotes and cancellations drop out for free,
  and a status added later keeps tracking. It deliberately does **not** gate
  on `Open_Status`: the `Hold` status carries `Open_Status = 0` but
  `Include_In_MRP = 1`, because held goods are still owed to a customer.
- **`Part_v_Flat_BOM` and `Part_v_BOM` extracted**, for BOM-exploded
  component demand. This is not optional decoration: verified 2026-09-09
  that **not one `33` part appears in the availability calculation without
  it** — they have neither containers nor direct sales orders, so their
  demand arrives entirely through the finished goods that consume them,
  which is exactly the population the OOS tile is about. Flat_BOM is
  pre-flattened (per-unit quantity already extended through intermediate
  levels), so this is a multiply-and-sum, not a recursive CTE.
- **Four availability columns published, not one.** `available_vs_orders`,
  `available_vs_total_demand` and the two `_firm_` variants, matching the
  four boxes in the screen's own "Available to Sell" panel — because which
  one is "Quantity Available" is a business definition. Same for the
  approval question: `PO_Status.Hold` separates orders that have cleared
  approval/deposit from those that haven't, and **the gap is material** — on
  `PlexTest`, part `93127-00MAXW1-1` carries 10,000 units of Pending Sales
  Approval demand against 1,500 of Pending Fulfillment. Both are exposed and
  flagged rather than silently resolved.
- **"Job Reqd" is deliberately absent.** It needs `Part_v_Job`/`Part_v_Job_Op`,
  0 rows on this tenant every time they have been checked; the column would
  be a confidently-wrong zero. First thing to add when jobs carry real rows.
- Verified live on `PlexTest`: **71 parts, 41 with inventory, 30 with real
  open demand totalling 508,807 units** (454,800 of it firm).

### Changed — `part_on_hand_inventory_report` matches Plex's Inventory Summary screen
- Adds **`revision`, `on_hand_weight`, `container_locations`, `unit` and
  `part_key`**, giving column-for-column parity with the VisionPlex
  "Inventory Summary" screen Amber named as the place to see on-hand
  (Part Number / Revision / Description / Containers / Quantity / Weight).
  Weight is `Net_Weight`, **not** `Gross_Weight` (which includes the
  container's own tare) nor `Part_Operation_Weight` (a per-operation
  standard, not what is physically in the container).
- **`part_key` exists so the container filter stops being copy-pasted.**
  `inventory_available_to_sell_view` reads this report instead of
  re-deriving on-hand for a third time — three copies of that filter is
  precisely how the `Active = -1` bug survived in all three at once.

### Changed — `inventory_out_of_stock_report` is now a filter, not a calculation
- Rewritten to `SELECT` from `inventory_available_to_sell_report` with
  Jennilyn's three conditions unchanged (`33%`, minimum quantity > 0,
  availability negative, excluding Custom). It uses the widest availability
  reading on purpose: for an out-of-stock **alert**, surfacing a part that a
  soon-to-be-approved order will exhaust beats finding out afterwards. The
  narrow figure ships beside it as `quantity_available_firm_only`.
- **Still expected to return 0 rows until the BOM extraction has run** —
  documented as such rather than presented as verified.

### Fixed — docs that were confidently wrong
- **`docs/CHEATSHEET.md`** — the out-of-stock rule said availability was
  "on-hand − allocated". Corrected, with the release-based demand model, the
  full `Include_In_MRP`/`Hold` status table, and the `Sales_v_PO_Line` has
  no quantity column trap added.
- **`docs/reports/part_on_hand_inventory_report.md`** — dropped two stale
  flags: "not yet verified against real quantities" (it reconciles exactly
  with Plex's Inventory Status Summary) and the open "Current QTY Available
  is on-hand minus something we can't find" question, which is now answered
  and has its own report.
- **`reports-list/supply-chain.md`** — the 2026-08-21 "Scheduled Job
  Requirements" lead (BOM explosion vs on-hand) is now half-built; recorded
  what differs, namely that this explodes sales-order demand rather than
  scheduled-job demand.

### Verified after deploy (same day, real run)
`terraform apply` + `plex-etl-sales-orders-test`, then every view queried
directly:

- **The Sep-4 price fix is finally verified.** `raw_Sales_v_Price` landed (4
  rows) and the two tiles that had read **$0 across 35,201 units** now carry
  real money: **WIP $43,723, Sales MTD $17,950.** That fix had been sitting
  unverified since Sep-4 purely because the extraction had never run.
- **BOM extraction works and was decisive.** 431 `Flat_BOM` rows, 137
  `Part_v_BOM` rows, **635,362 units of BOM-exploded component demand across
  11 parts.** Before it, no `33` part appeared in the availability view at
  all; after it, `33127-01VOXNU-1` shows **305,000 units of demand and
  −305,000 availability.**
- **The flat-BOM quantity assumption checked out as far as this tenant
  allows:** 81 (parent, component) pairs exist in both the flat and
  single-level BOM and the quantities are **identical on all 81**, with
  **max BOM_Level = 1**. The multi-level case remains unproven because no Vox
  BOM is deeper than one level yet — noted in the SQL header rather than
  claimed as verified.
- **`inventory_out_of_stock_report` still returns 0, and now for a precise
  reason that is not a bug:** both `33` parts on the tenant have
  `Minimum_Inventory_Quantity = 0`, which the rule treats as "not assigned".
  The part short by 305,000 units is therefore correctly excluded. **The
  report cannot fire for anything until minimum inventory quantities are
  entered in Plex** — data entry, not code. An earlier count of "7 parts, 5
  with a minimum above zero" predates a `PlexTest` reset and cannot be
  reconciled against current data.

### Fixed — the test pipeline has its own config file, which the first deploy missed
- `reports/test/sales_orders.yaml` is a **separate file** from
  `reports/sales_orders.yaml` (Terraform's `sales_orders_config_test` points
  at it), so the first apply + run loaded **22 extractions, not 24** and
  silently produced no BOM tables at all while still exiting 0. Both files now
  carry the two BOM extractions and the new `bq_view`, in the same order.
  **Any change to a pipeline's extraction or view list has to be made in both
  files** — the test config is not generated from the prod one.

### Notes
- **Finished goods have no on-hand stock at Vox**, confirmed in both the live
  Plex screens and BigQuery — everything sits as components, packaging and
  WIP, because Vox builds to order. So an FG part with an open order shows
  negative availability, correctly. Worth knowing before anyone reports it
  as a bug.
- `Part_v_Flat_BOM` was created in both datasets with its real ODBC-declared
  schema ahead of the first extraction, so the new view could be dry-run and
  queried before deploy rather than "checked against a stub". The ETL
  overwrites it on the next run.

## 2026-09-04 (later)

### Fixed — inventory reported 0 rows for weeks because two filters were inverted
- **`Part_v_Container.Active` and `Part_v_Container_Status.OK_Status` hold
  `1/0`, not `-1`.** Three views — `part_on_hand_inventory_view`,
  `inventory_out_of_stock_view`, `inventory_risk_analysis_view` — filtered
  `= -1` and therefore matched **nothing**. `raw_Part_v_Container` had **122
  real rows** the entire time. Every doc, including this changelog and
  `docs/CHEATSHEET.md`, had been repeating "upstream extract still empty" as
  the explanation. It never was.
- **`docs/CHEATSHEET.md`'s boolean table was the source of the error** and is
  now corrected, with a warning that the `Part_v_*` / `Sales_v_*` split is not
  a reliable guide — the column has to be checked. The original entry cited a
  2026-08-11 "confirmed live" note, which is exactly how a wrong fact survives.
- **The status test is no longer `OK_Status`,** because it cannot express Vox's
  rule (Jennilyn, Sep-4): on-hand = **Hold + Inspection Required + OK + Hold
  for Design Order**, excluding **Defective and Expired**. Against the real
  lookup `OK_Status` is **0 on Hold and Inspection Required** (which must be
  included) and **1 on Allocated, Loaded, Shipped and Staged** (which must not
  be, or shipped goods count as on-hand). The four statuses are now named
  explicitly.
- **Dropped the `Container_Status` lookup join.** Nothing selected from it, and
  the extracted copy is **stale**: Plex has 16 statuses including
  `HOLD FOR DESIGN ORDER` (key 10281); the raw table has 15 and is missing
  exactly that one. An INNER join would silently drop containers in any status
  the stale lookup hasn't caught up with — the same failure already fixed in
  the 4 Daily Reports. Filtering on the container's own status string avoids it.
- **Verified against Plex's own UI.** The corrected view returns
  **1,164 OK + 2 Hold = 1,166 active containers**, matching Vox's "Inventory
  Status Summary" screen exactly (OK 99.83%, Hold 0.17%, total 1,166). 91
  inactive Hold containers are correctly excluded.

### Added — sales order LINE price, fixing the $0 tiles
- **`Sales_v_Price` extracted** (keyed on `PO_Line_Key`) and wired into
  `sales_mtd_by_status_change_view`, `sales_order_value_by_status_view` and
  `pipeline_plex_value_view` as the **primary** price, with
  `Part_v_Customer_Part_Price` demoted to fallback.
  Jennilyn, Sep-4: *"No, it'll always have a price in there. So it needs to be
  the line item price."* The customer price list matched nothing for the 7 real
  Pending Fulfillment orders, which is why WIP and Sales MTD both read **$0
  across 35,201 real units** — not a broken join, since quote-stage orders
  priced fine through it ($900,975); those parts simply have no list row.
- Each view now exposes **`price_from_fallback_list`** so a row priced off the
  generic list rather than its own order line is visible, not silently mixed in.
- Tier rule: prefer `Primary_Price`, then lowest `Breakpoint_Quantity`, then
  most recent `Effective_Date`; inactive rows dropped.

### Added — real goals loaded, and they already existed
- **`VoxScorecardsLive.sales_goals` is a real maintained table** — 8 reps x 7
  months (Jun-Dec 2026) — and the company-wide monthly figures were sitting
  hardcoded as a 12-row `UNION ALL` inside `vw_sales_mtd_vs_goal`'s SQL. Both
  were loaded into `scorecard_goals` **by query, not retyped**, so there is no
  transcription risk. 4 placeholder rows deleted; 68 real rows in.
- **Nothing was fabricated to fill the gaps.** Revenue and production goals
  stay EMPTY because no real source exists for either — both live in Google
  Sheets nobody has exported. Entering the scorecard's rounded display values
  ($4.7M, 100.00M) would have made every "% to Goal" subtly wrong forever with
  nothing recording where the numbers came from.
- **A discrepancy worth surfacing:** the company-wide September goal is
  **$5,040,000**, but the eight per-rep goals sum to **$4,690,000**. Two
  different numbers, both currently driving the live scorecard. Loaded both,
  distinguished by `scope`, and flagged rather than reconciled.
- Verified end to end: `sales_vs_goal_report` now returns all 8 reps plus
  `(company-wide)` with real targets at 0% (the test tenant has no rep-assigned
  sales), and `(no rep assigned)` — the test data — correctly flagged
  `sales_without_goal`. The FULL OUTER JOIN is doing exactly what it was built
  for.

### Changed — ready-to-ship is no longer priced off a guess
- `shipping_pending_revenue_view` now prefers **shipper price → sales ORDER
  LINE price → customer list**, and exposes **`price_source`** naming which was
  used. The Shipper_Line → Release → PO_Line bridge was already in the view, so
  the order-line key was sitting there unused. This substantially answers the
  open "estimate or units only?" question: the order line's own agreed price is
  neither a guess nor unavailable before shipment.

### Research — three open questions answered from data, not opinion
- **Work centre groups confirmed:** Blending, Bottling, Encapsulating,
  Labeling, Pre-Weigh, Preparation, Printing, Rework. Bottling and Labeling
  match the tile names exactly; only "Encapsulation" differs (`Encapsulating`).
- **Two-rep orders don't exist yet** — 0 of the orders carrying a rep have more
  than one, so the credit-split question is currently moot.
- **Ship date vs invoice date is currently moot too** — on the one shipped line
  they are identical, and no shipped line lacks an invoice date.
- **The out-of-stock count lines up:** Plex has **7 parts starting with 33 and
  exactly 5 with a minimum quantity above zero** — matching the count of 5 on
  Jennilyn's own sheet. On-hand is fixed; the only missing piece is the
  sold/demand figure, and `raw_Sales_v_Release_Allocation` has **0 rows in both
  environments**.
- **Container statuses:** `Rework` carries `Include_In_MRP = 1` (Plex treats it
  as available supply) while `Lab Analysis - Sample (Shipped)` carries `0` and
  its name says the sample has gone. Recommended include/exclude respectively —
  neither currently holds a container, so the stakes are low.

### Notes
- All six modified views dry-run clean. `terraform plan`: **0 to add, 8 to
  change, 0 to destroy.** Not applied — apply is blocked by the local
  permission classifier.
- The price fix **cannot be verified until the extraction runs**, since
  `raw_Sales_v_Price` does not exist yet. Syntax was checked against a stubbed
  table. Re-verify after the next `plex-etl-sales-orders-test` run.

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
