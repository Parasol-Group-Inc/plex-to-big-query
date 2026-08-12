# MFG Job Schedule

- **Link:** https://docs.google.com/spreadsheets/d/1xqccqPwPA37291vJOpxNZhBGiyy_xbp4TPoW0UMyozA/edit
- **Type:** Google Sheet
- **Category:** Product Release Tracking / Forecasting
- **Departments:** Production, Supply Chain, Sales, Quality
- **Status:** ✅ Built — 3 reports deployed to GCP, verified live
- **Technical build log:** [docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md](../docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md)

## Tabs in this spreadsheet

This is a multi-tab spreadsheet — this doc covers the **"Open"** tab only.
Other tabs are tracked separately since a tab can have its own grain, its
own gaps, and even feed a different downstream report than the main tab.

| Tab | Status | Detail Doc |
|---|---|---|
| Open | ✅ Built | this doc |
| YTD Gate Stats | 🔍 Mapped | [mfg_job_schedule_ytd_gate_stats.md](mfg_job_schedule_ytd_gate_stats.md) |
| FG Testing Pending | 🔍 Mapped | [mfg_job_schedule_fg_testing_pending.md](mfg_job_schedule_fg_testing_pending.md) |
| YTD List | 🔍 Mapped | [mfg_job_schedule_ytd_list.md](mfg_job_schedule_ytd_list.md) |
| READ ME | 📄 Reviewed — not data, but confirmed/corrected several findings | [mfg_job_schedule_read_me.md](mfg_job_schedule_read_me.md) |
| Done YTD | 🔍 Mapped | [mfg_job_schedule_done_ytd.md](mfg_job_schedule_done_ytd.md) |
| Done 2025 | ⏳ Pending | — |
| 2025 List | ⏳ Pending | — |
| Success | ⏳ Pending | — |
| Inventory Availability | ⏳ Pending | — |

## ❓ Open Questions for the Data Architect/Scientist

Running list across all tabs of this spreadsheet — kept in one place so
there's a single list to bring to that conversation rather than one per
tab. Full context for each lives in the linked tab doc.

1. Is "TAT Stats & Success" (named in the READ ME's automation
   description) the same tab as "YTD Gate Stats," an old/renamed version
   of it, or a distinct tab not yet seen? — [mfg_job_schedule_read_me.md](mfg_job_schedule_read_me.md)
2. Confirm the Yield formula (`Caps Made ÷ Capsule Count`) holds for
   Blending-only jobs with no encapsulation step. — [mfg_job_schedule_read_me.md](mfg_job_schedule_read_me.md)
3. ✅ **Resolved 2026-08-11**: "Days to Mfg"/"Total Days" =
   `FG Testing Released − Date Entered`, confirmed by exact match against
   real data; the 2 negative values are legitimate rework/partial-batch
   rows, not bad data. — [mfg_job_schedule_done_ytd.md](mfg_job_schedule_done_ytd.md)
4. Confirm the job-level "Successful" threshold in Gate Stats' Table 1 —
   perfect 3/3 Success Rating, or a lower bar? — [mfg_job_schedule_ytd_gate_stats.md](mfg_job_schedule_ytd_gate_stats.md)
5. Confirm the exact TAT goal boundary (evidence points to ≤84 days /
   12 weeks; no sample row lands on 85 to pin it exactly). — [mfg_job_schedule_ytd_list.md](mfg_job_schedule_ytd_list.md)
6. Is it worth automating Custom/Stock from Plex (`Job_Type_Key`/
   `Job_Distribution.Release_Key`, both unvalidated against real data) —
   given it's currently a manual SKU-column convention, not a system
   field? — [mfg_job_schedule_read_me.md](mfg_job_schedule_read_me.md)
7. How should the 95%/92%/84-day goal thresholds be stored if this ever
   gets built, given they're editable in the sheet and explicitly
   non-retroactive? — [mfg_job_schedule_read_me.md](mfg_job_schedule_read_me.md)
8. Locate a real Plex source for "Blender" (batch size, e.g. `2000L`) —
   checked `Part_v_Job_Material`, wrong table. — [mfg_job_schedule_fg_testing_pending.md](mfg_job_schedule_fg_testing_pending.md)
9. Should any future build sanity-bound the 8 stage-to-stage interval
   columns (Entered→POs Received, etc.)? Real data shows year-typo rows
   producing million-day intervals — the source sheet doesn't guard
   against this either. — [mfg_job_schedule_done_ytd.md](mfg_job_schedule_done_ytd.md)

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
