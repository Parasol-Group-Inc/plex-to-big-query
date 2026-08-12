# MFG Job Schedule Report Build Plan

Source of truth for a manually maintained "MFG Job Schedule - Open" tracking
spreadsheet (blending/encapsulation production board: raw-material sourcing
status, lot/QC tracking, equipment/room assignment). Goal: make every column
that's genuinely sourceable from Plex available as a BigQuery view via the
existing `reports/*.yaml` + `reports/sql/*.sql` pipeline pattern (see
[docs/CHEATSHEET.md § How to Add a New Report](CHEATSHEET.md#how-to-add-a-new-report)),
and be explicit about the columns that aren't — rather than guess at them.

## Round 1 (2026-08-11): column-by-column mapping

Every column in the tracker was checked against the real Plex ODBC catalog
(`catalog/*.md`) and, where a candidate view existed, against live schema on
`vox.test.odbc.plex.com`. Full detail lives in
[[project-plex-data-sources]] (memory) and in the "Confirmed Live" sections
added to `catalog/plex_part_views_catalog.md`,
`catalog/plex_quality_views_catalog.md`, `catalog/plex_common_views_catalog.md`,
`catalog/plex_maintenance_views_catalog.md`, and
`catalog/plex_warehouse_views_catalog.md`.

**Confirmed buildable from Plex:**

| Tracker column | Plex source |
|---|---|
| SKU, Description | `Part_v_Part.Part_No`, `.Name` |
| Qty Ordered | `Part_v_Job.Quantity` |
| Blending/Encap Started/Complete, Date Complete | `Part_v_Job_Op.Start_Date`/`Complete_Date` (workcenter/type exposed, not hardcoded to a name pattern — see Round 2) |
| Operator | `Part_v_Job_Op.Started_By`/`Completed_By` → `Personnel_v_Employee.Common_Name` |
| Lot #, lot manufactured date | `Part_v_Job.Lot_Key` → `Part_v_Lot` |
| NC # | `Quality_v_Problem` |
| Raws Sampled/Released/FG Testing Released (closest analog) | `Quality_v_Checksheet`/`Checksheet_Status` |
| Room # | `Part_v_Job.Building_Key` → `Common_v_Building` |
| Asset # | `Part_v_Job_Op.Workcenter_Key` → `Maintenance_v_Equipment.Workcenter_Key` |
| Available Inventory | `Part_v_Container` (see Round 1 finding below) |
| POs Received | Already live — `purchasing_open_orders_report` |

**Round 1 finding — on-hand inventory isn't in the Warehouse module.**
`Warehouse_v_Part_Quantity` (the intuitive guess) doesn't exist — confirmed
live: `Base table ... not found`. The real carrier is **`Part_v_Container`**,
under the **Part** module: `Part_Key`, `Quantity`, `Location`,
`Container_Status`, `Active`. Sum `Quantity` per part, filtered to
active/OK-status containers via `Part_v_Container_Status.OK_Status`.

**Deliberately excluded — no Plex source exists or ever will:**

| Tracker column | Why excluded |
|---|---|
| Job # (NetSuite `WO00xxxxx`) | Genuinely a different system. No FK between NetSuite WO numbers and Plex `Job_No` — cross-referencing the two requires matching on **SKU + date proximity**, not a key join, and NetSuite isn't a data source this pipeline reads from. Documented here as guidance for whoever needs to do that correlation manually or in a future NetSuite-side integration; not implemented in this repo. |
| Date Entered, Days in WIP, Days Left, BR Ready for MFG, Sign Off, Notes | Manual/human judgment fields — a running commentary log and business-process gates that don't correspond to any ERP-tracked value. These stay in the spreadsheet; no column was added for them, and none should be fabricated as `NULL` placeholders. |
| MG Per Cap, Cap Specs (e.g. "00 Veggy") | Plausible sources exist (`Part_v_BOM`, `Part_v_Part_Attribute`) but computing an actual dosage-per-capsule number requires a unit conversion (mg vs. g vs. kg) that isn't reliably inferable from schema alone, and wasn't part of this round's scope. Flagged as a follow-up, not built speculatively. |

## Round 2 (2026-08-11): built as sibling views on existing pipelines, not parallel reports

**Key decision:** `work_orders.yaml` already extracts `Part_v_Job`,
`Part_v_Job_Op`, `Part_v_Workcenter`, and `Part_v_Part` (shared) at the same
grain this tracker needs (one row per job operation). Building a second,
parallel report would have re-extracted the same tables and fragmented the
story. Instead:

- **`mfg_job_schedule_report`** was added as a **second `bq_view` entry** on
  the existing `work_orders.yaml` pipeline (using the `bq_view`-list support
  built for the NetSuite reports — see `docs/NETSUITE_REPORT_BUILD_PLAN.md`
  Round 2). 8 new extractions were added (`Part_v_Job_Status`,
  `Personnel_v_Employee`, `Part_v_Lot`, `Part_v_Lot_Shelf_Life`,
  `Quality_v_Checksheet`, `Quality_v_Checksheet_Status`,
  `Maintenance_v_Equipment`, `Common_v_Building`); the original
  `work_orders_report` view is untouched. SQL: `reports/sql/mfg_job_schedule_view.sql`.
- **`quality_nonconformance_report`** — new standalone report (new Cloud Run
  job), single extraction (`Quality_v_Problem`), reusing shared
  `raw_Part_v_Part`. `Problem_Category`/`Problem_Status`/`Problem_Type`/
  `Defect_Type` are all inline text directly on `Quality_v_Problem` — same
  "no `_Key` suffix = inline text, not an FK" pattern already confirmed on
  `Part_v_Part.Part_Status`, so no lookup joins were needed. **No
  `Job_Key`/`Job_Op_Key` on this view** — an NC links to a part, not a
  specific job; cross-referencing to a schedule row needs the same
  part+date correlation as the NetSuite Job # gap above.
- **`part_on_hand_inventory_report`** — new standalone report (new Cloud Run
  job), extracts `Part_v_Container` + `Part_v_Container_Status`. On-hand qty
  = `SUM(Quantity)` grouped by part, filtered to `Active = -1` and
  `OK_Status = -1`. Joined the two tables on `Container_Status` as **text**,
  not cast to `INT64` — same inline-text lesson as above; casting a text
  column to `INT64` would compile (`SAFE_CAST` never errors) but silently
  match zero rows once real data appears.

**Real data appeared during testing** (unusual for this project — most prior
live checks hit empty test tables): `Part_v_Job_Op` returned 4 real rows,
confirming workcenter names `'Preweigh 1'` and `'Blend 2'`, both
`Workcenter_Type = 'Batch'`, and job statuses `'Production'`/`'Scheduled'`.
This validates the earlier guess about blending workcenter naming, but
**"Encap"-style naming still has zero live evidence** — so
`mfg_job_schedule_view.sql` deliberately does not hardcode a
Blending-vs-Encapsulation classification. It exposes `workcenter`/
`workcenter_type` as plain columns; filter on those once more real
workcenter names are visible.

**Bug hit and fixed during testing:** joining an already-populated table
(real `INT64` key) against a table that was empty at extraction time
(BigQuery auto-creates those all-`STRING`) throws
`No matching signature for operator = for argument types: INT64, STRING`
unless **both** sides are cast — casting only the populated side compiles
but would never match. Hit on `Part_v_Lot`, `Part_v_Lot_Shelf_Life`, and
`Maintenance_v_Equipment` (all empty on this test run).

## Status summary

| Report | Status | Notes |
|---|---|---|
| `mfg_job_schedule_report` | ✅ Built, verified live | Second `bq_view` on `work_orders.yaml`/`work_orders_test`. 4 real rows returned during local BigQuery testing against `PlexTest`. |
| `quality_nonconformance_report` | ✅ Built, verified live | New pipeline, compiles and queries cleanly (0 rows — no NC records on test tenant currently). |
| `part_on_hand_inventory_report` | ✅ Built, verified live | New pipeline, compiles and queries cleanly (0 rows — `Part_v_Container` empty on test tenant currently). |

All three were verified by running the actual extraction + `CREATE OR
REPLACE VIEW` against real BigQuery `PlexTest` locally via Docker (ADC
credentials, `GCP_PROJECT=voxdatalake`), not just checked for SQL syntax.

## How this was confirmed

Same method as `docs/NETSUITE_REPORT_BUILD_PLAN.md`: throwaway scripts that
`import main as m` and call `m.get_odbc_connection()` / `cursor.execute()`
directly (bypassing `main.py`'s local-CSV-mode, which skips output on 0 rows
and would hide column names). For the BigQuery side, `docker compose run`
with `OUTPUT_MODE=bigquery`, `GCP_PROJECT=voxdatalake`, `BQ_DATASET=PlexTest`,
and the host's `gcloud auth application-default` credentials mounted in,
against a scratch copy of each report YAML with `sql_file` pointed at the
local `reports/sql/` path instead of `gs://`. All scratch files were deleted
after use; nothing scratch-only was committed.

## Round 3 (2026-08-11): multi-tab mapping — this spreadsheet has 10 tabs

The "Open" tab covered above is one of 10 tabs on this spreadsheet (see
`spreadsheets/mfg_job_schedule.md`'s "Tabs in this spreadsheet" tracker).
Each tab gets its own mapping doc (`spreadsheets/mfg_job_schedule_<tab>.md`):

- **YTD Gate Stats** — a monthly Stock/Custom success-rate rollup (Yield +
  Deviations/NCs + TAT). Not buildable — Emilio's own call, given how many
  gaps it inherits (NC-to-job correlation, unconfirmed Yield, an undefined
  "Successful" composite rule). Syncing with the data architect on these
  separately rather than building around guesses.
- **FG Testing Pending** — same job-level grain as Open, filtered to jobs
  awaiting FG testing release. Mostly reuses Open's confirmed sources.
  Real data on this tab corrected an earlier mistake: `Part_v_Job.Job_Type`
  (checked on the YTD Gate Stats pass) doesn't exist, but
  `Part_v_Job.Job_Type_Key` does, joining to a real `Part_v_Job_Type`
  lookup (`Stock`/`Service`/`Pre-Production`/`Rework`) — missed on the
  first pass. `Part_v_Job_Distribution.Release_Key` is a second,
  independent lead for the same Stock-vs-Custom question.

Both leads were added to `mfg_job_schedule_view.sql` as `job_type`,
`job_distribution_count`, `job_distribution_sample_release_key` — exposed
as raw signal, not collapsed into an asserted Stock/Custom boolean, since
`Job_Distribution` is still empty on the test tenant. Local BigQuery test
against `PlexTest` partially validated this already: 2 job records left
over from a prior extraction (Plex itself returns 0 rows right now) both
resolved `job_type = 'Stock'` through the new join — the join mechanics
work on real data, not just schema. Committed (`6c3b1c7`), **deployed
2026-08-11** alongside Round 4 below (see Deployment note).

## Round 4 (2026-08-11): exploratory goal-check columns, once all 10 tabs were mapped

After every tab was reviewed (see `spreadsheets/mfg_job_schedule.md`'s
tracker), Emilio asked what's buildable without waiting on the data
architect conversation. Answer: the "Success" tab is a literal 4×4 config
table (Yield ≥95%/92% stock/custom, Total Days ≤84, weighted 1/3 each) —
confirmed thresholds, not inference. Added to `mfg_job_schedule_view.sql`:

- `yield_pct` — `Job_Op.Quantity ÷ Job.Quantity`, mirrors the confirmed
  `Caps Made ÷ Capsule Count` formula from the sheet, computed per
  operation row (not isolated to a specific "final output" operation).
- `yield_meets_goal` — `yield_pct` vs. 0.95/0.92, threshold picked by the
  unconfirmed `job_type = 'Stock'` lead.
- `job_add_date` — `Part_v_Job.Add_Date`, a stand-in for the sheet's
  manually-typed "Date Entered" (no Plex equivalent exists at all).
- `total_days_from_job_creation` / `tat_meets_goal` — `job_add_date` to
  the most recent QC checksheet's `Inspection_Date` (itself an
  approximate analog for "FG Testing Released"), checked against the
  confirmed 84-day threshold.

All explicitly flagged in the SQL header as **exploratory** — two of the
three formula inputs are themselves speculative stand-ins, so these
columns don't reproduce the sheet's actual Success Rating/Grade, just
approximate it using Plex-native dates. The query was restructured around
a `base` CTE so these derived columns reference plain values instead of
repeating BigQuery's raw date-conversion expressions three times each.
Tested against real BigQuery under a scratch view name before deploying —
compiled cleanly, `job_add_date` resolved a real date (`2026-07-17`) from
Plex, and every derived column returned `NULL` gracefully where an input
was missing.

## Deployment

Terraform: `mfg_job_schedule_report` needs no new Cloud Run job (rides the
existing `plex-etl-work-orders(-test)` schedule, 4/5 AM UTC) — only the new
`work_orders.yaml`/`test/work_orders.yaml` and the new SQL file need
re-uploading to GCS, which `terraform apply` does automatically since it
tracks those files by content hash. `quality_nonconformance` and
`part_on_hand_inventory` are new Cloud Run jobs + schedulers, scheduled
14/15 and 16/17 UTC respectively (next free slots after the existing 4–13
UTC block). See `terraform/main.tf` for the exact resources.

**Round 3 + Round 4 deployed together, 2026-08-11** — held per Emilio's
request until all 10 tabs were mapped, then batched into one
`terraform apply` (`work_orders_config_prod`/`_test`,
`mfg_job_schedule_view_sql` — clean 3-object update, 0 add/0 destroy) once
he confirmed which buildable-now items to ship. Verified live: triggered
`gcloud run jobs execute plex-etl-work-orders-test --wait` (succeeded),
then queried the deployed `PlexTest.mfg_job_schedule_report` directly to
confirm `job_type`, `job_add_date`, and the other new columns are present
and computing correctly in production, not just in the scratch test.
