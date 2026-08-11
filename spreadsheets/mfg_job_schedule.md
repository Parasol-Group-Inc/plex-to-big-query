# MFG Job Schedule

- **Link:** https://docs.google.com/spreadsheets/d/1xqccqPwPA37291vJOpxNZhBGiyy_xbp4TPoW0UMyozA/edit
- **Type:** Google Sheet
- **Category:** Product Release Tracking / Forecasting
- **Departments:** Production, Supply Chain, Sales, Quality
- **Status:** ✅ Built — 3 reports deployed to GCP, verified live
- **Technical build log:** [docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md](../docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md)

## What it is

A manually maintained production board (tab: "MFG Job Schedule - Open")
tracking blend/encapsulation jobs from raw-material sourcing through QC
release: dates, blender/workcenter assignment, lot numbers, NC numbers,
equipment/room, and a running free-text commentary log per job.

## Findings — column-by-column

**Buildable from Plex (confirmed live, `vox.test.odbc.plex.com`):**

| Column | Plex source | Report |
|---|---|---|
| SKU, Description | `Part_v_Part.Part_No`/`.Name` | `mfg_job_schedule_report` |
| Qty Ordered | `Part_v_Job.Quantity` | `mfg_job_schedule_report` |
| Blending/Encap Started/Complete, Date Complete | `Part_v_Job_Op.Start_Date`/`Complete_Date`, filterable by workcenter — **full workcenter roster confirmed live 2026-08-11**: `Blend 2-5` (Batch) and `Encapsulation 1-10` (Primary) are both real, distinct workcenter groups, resolving the gap noted below | `mfg_job_schedule_report`, `work_orders_report` |
| Operator | `Job_Op.Started_By`/`Completed_By` → `Personnel_v_Employee.Common_Name` | `mfg_job_schedule_report` |
| Lot #, lot manufactured date | `Part_v_Job.Lot_Key` → `Part_v_Lot` | `mfg_job_schedule_report` |
| NC # | `Quality_v_Problem` | `quality_nonconformance_report` |
| Raws Sampled/Released/FG Testing Released (closest analog) | `Quality_v_Checksheet`/`_Status` | `mfg_job_schedule_report` |
| Room # | `Part_v_Job.Building_Key` → `Common_v_Building` | `mfg_job_schedule_report` |
| Asset # | `Job_Op.Workcenter_Key` → `Maintenance_v_Equipment.Workcenter_Key` | `mfg_job_schedule_report` |
| Available Inventory | `Part_v_Container` (on-hand qty carrier — NOT under the Warehouse module, `Warehouse_v_Part_Quantity` doesn't exist) | `part_on_hand_inventory_report` |
| POs Received | Already live | `purchasing_open_orders_report` |

**Gaps — plausible source exists but unresolved, or genuinely absent:**

| Column | Gap |
|---|---|
| Blending vs. Encapsulation classification | **Resolved 2026-08-11** — both `Blend 2-5` and `Encapsulation 1-10` workcenter names confirmed live (see `reports-list/production.md`). No hardcoded classification is built into the SQL yet (still exposes raw `workcenter`/`workcenter_type` columns), but a `WHERE workcenter LIKE 'Encapsulation%'`/`'Blend %'` filter is now known to work — ask if you want this formalized into named columns. |
| MG Per Cap, Cap Specs (e.g. "00 Veggy") | `Part_v_BOM` / `Part_v_Part_Attribute` are plausible sources, but turning BOM component quantities into an actual per-capsule dosage needs a unit conversion (mg/g/kg) not reliably inferable from schema alone. Not built — flagged as a follow-up. |
| NC-to-job correlation | `Quality_v_Problem` has no `Job_Key`/`Job_Op_Key` — an NC links to a part, not a specific job. Cross-referencing to a schedule row needs a part+date match, not a join key. |

**Manual-only — never in any ERP, deliberately not built:**

Job # (these are **NetSuite** WO numbers, e.g. `WO0046335` — no FK to Plex
`Job_No`; correlating the two systems needs a SKU+date match, and NetSuite
isn't a data source this pipeline reads from at all), Date Entered, Days in
WIP, Days Left, BR Ready for MFG, Sign Off, and the free-text Notes column
(a running human commentary log).

## Reports produced

- `mfg_job_schedule_report` — second `bq_view` on the existing
  `plex-etl-work-orders(-test)` job (4/5 AM UTC)
- `quality_nonconformance_report` — `plex-etl-quality-nonconformance(-test)`
  (2/3 PM UTC)
- `part_on_hand_inventory_report` — `plex-etl-part-on-hand-inventory(-test)`
  (4/5 PM UTC)

See [docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md](../docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md)
for the full technical narrative (SQL design decisions, bugs hit and fixed,
how live verification was done).
