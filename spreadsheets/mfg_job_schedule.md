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
| Done 2025 | 🔍 Mapped | [mfg_job_schedule_done_2025.md](mfg_job_schedule_done_2025.md) |
| 2025 List | 🔍 Mapped | [mfg_job_schedule_2025_list.md](mfg_job_schedule_2025_list.md) |
| Success | ✅ Fully resolved | [mfg_job_schedule_success.md](mfg_job_schedule_success.md) |
| Inventory Availability | 🔍 Mapped | [mfg_job_schedule_inventory_availability.md](mfg_job_schedule_inventory_availability.md) |

**All 10 tabs now reviewed.** See the Open Questions list below for what's
still genuinely open across the whole spreadsheet — everything else has
either been built, confirmed, or explicitly ruled out.

**Built and deployed 2026-08-11, without waiting on the open questions
below:** `job_type`/`job_distribution_count`/`job_distribution_sample_release_key`
(the Stock/Custom leads), plus exploratory `yield_pct`/`yield_meets_goal`
and `job_add_date`/`total_days_from_job_creation`/`tat_meets_goal` (using
the confirmed Success-tab thresholds, with two speculative stand-in
inputs — see `docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md` Round 4). All live on
`mfg_job_schedule_report`, verified against real BigQuery. Deviation
couldn't be added the same way — the NC-to-job correlation gap (Open
Question, `Quality_v_Problem` has no job FK) blocks it structurally, not
just for lack of data.

## ❓ Open Questions for the Data Architect/Scientist

Running list across all tabs of this spreadsheet — kept in one place so
there's a single list to bring to that conversation rather than one per
tab. Full context for each lives in the linked tab doc.

**New to the terminology?** Start with
[mfg_job_schedule_open_questions_explained.md](mfg_job_schedule_open_questions_explained.md)
— a plain-language walkthrough of every item below (what it means, why it
matters, what a good answer looks like), plus a short glossary for terms
like Job Operation, Yield, TAT, and foreign key. It also calls out one
important gap that isn't numbered below: `Quality_v_Problem` has no
foreign key to a job, which blocks the Deviation/NC gate structurally,
not just for lack of data.

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
5. ✅ **Resolved 2026-08-11**: TAT goal is exactly `Total Days ≤ 84` for
   both stock and custom — confirmed by real-data inference (2 rows
   landing exactly on 85, both failing) **and** by the literal source
   config in the "Success" tab, which states `84` outright. — [mfg_job_schedule_success.md](mfg_job_schedule_success.md)
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
10. What's the actual archiving boundary between "Done YTD" and
    "Done 2025"? Not determinable from the data — some late-2025
    completions appear in Done 2025 while Done YTD starts 9/17/2025. — [mfg_job_schedule_done_2025.md](mfg_job_schedule_done_2025.md)
11. Should rework rows be included in monthly stats consistently? Real
    data shows both practices today: some rework rows get a deliberately
    deleted date ("not in stats, this is a rework"), others are left in
    with a negative Total Days. — [mfg_job_schedule_done_2025.md](mfg_job_schedule_done_2025.md)
12. What does "BR Ready for MFG" actually represent? Real values are
    small integers (1-3) and occasionally a comma-pair like `2,5` — no
    clear pattern against any other mapped column. — [mfg_job_schedule_done_2025.md](mfg_job_schedule_done_2025.md)
13. Where do "Avg Daily" (usage rate) and "Reorder Point" actually come
    from? Checked the obvious Plex candidates live and ruled all of them
    out (`Part_v_Part_Planning_Parameters` has the wrong columns; 4
    speculative Material-module view names don't exist) — likely outside
    Plex entirely (NetSuite demand planning, or a sheet-side historical
    average). — [mfg_job_schedule_inventory_availability.md](mfg_job_schedule_inventory_availability.md)
14. Is "Current QTY Available" = "Quantity On Hand" minus something
    allocated/committed? `Part_v_Inventory_Allocation` exists but has no
    `Quantity`/`Part_Key` column to net against — checked, not a direct
    join. — [mfg_job_schedule_inventory_availability.md](mfg_job_schedule_inventory_availability.md)

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
| NC-to-job correlation | `Quality_v_Problem` has no `Job_Key`/`Job_Op_Key` — an NC links to a part, not a specific job. Cross-referencing to a schedule row needs a part+date match, not a join key. **New lead, confirmed live 2026-08-12**: `Quality_v_Claim` is a distinct Quality entity that carries `Job_Key`/`Part_Key`/`Service_Job_Key` directly — schema confirmed against the live tenant, but the view is empty ("No Records Were Found"), so the `Job_Key` join can't be tested yet. Also unconfirmed whether the sheet's "NC #" column actually refers to a Claim rather than a Problem — `Claim` reads as formal customer/supplier complaint intake, not necessarily 1:1 with a shop-floor NC. See `catalog/plex_quality_views_catalog.md`. |
| Days Left | **Corrected 2026-08-11** — moved out of manual-only. Mapping the "Inventory Availability" tab found its exact formula (`Current QTY Available ÷ Avg Daily`, confirmed against real data), but the one input it needs — `Avg Daily` (average daily usage rate) — has no confirmed Plex source. Checked `Part_v_Part_Planning_Parameters` (real view, wrong columns — MRP/scheduling flags, not a usage rate) and 4 speculative view names (all don't exist). See `mfg_job_schedule_inventory_availability.md`. |

**Manual-only — never in any ERP, deliberately not built:**

Job # (these are **NetSuite** WO numbers, e.g. `WO0046335` — no FK to Plex
`Job_No`; correlating the two systems needs a SKU+date match, and NetSuite
isn't a data source this pipeline reads from at all), Date Entered, Days in
WIP, BR Ready for MFG, Sign Off, and the free-text Notes column (a
running human commentary log).

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
