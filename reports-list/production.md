# Reports List — Production

Source file: `Reports List - Production.csv`. Columns: Report Name,
Source, Function, Users, Link, Priority, Plex Report Equiv.

This tab has the heaviest overlap with [`spreadsheets/`](../spreadsheets/) —
most rows here already have (or now have) their own detail doc there.

| Report | Source | Status | Notes |
|---|---|---|---|
| MFG Job Schedule | Google Sheet | ✅ Already built | See `spreadsheets/mfg_job_schedule.md` |
| Encap Daily Report | Google Sheet | 🔍 Mapped | "Plex Report Equiv" claims Production Yield (ActionKey 7346) "works for part of it" — verdict: **worst fit of the 4 Daily Reports**, no weight concept at all. See `spreadsheets/encap_daily_report.md` |
| Packaging Daily Report | Google Sheet | 🔍 Mapped | Same Production Yield claim — verdict: **weak fit**. See `spreadsheets/packaging_daily_report.md` |
| Labeling Daily Report | Google Sheet | 🔍 Mapped | Same claim — verdict: **weak fit**. See `spreadsheets/labeling_daily_report.md` |
| Blending Daily Report | Google Sheet | 🔍 Mapped | Same claim — verdict: **weakest-but-most-plausible fit** (genuine weighing workflow). See `spreadsheets/blending_daily_report.md` |
| Bottling Job Schedule | Google Sheet | 🔍 Mapped | Sibling of MFG Job Schedule, bottling-specific. See `spreadsheets/bottling_job_schedule.md` |
| Weekly Production Update | Google Sheet | ⏳ Pending | No content provided yet. Users: "Mark, Nick, Chris" |
| Rolling TAT Report | NetSuite + GSheet | ✅ Deployed, best-criteria — needs data-scientist input | Same underlying concept as mapping-doc #70 "Turn Around Time Report - Rolling". Built as `quality_turnaround_time_report` (bq_view on `quality_nonconformance.yaml`) — per-record `Closed_Date - Problem_Date` in days, with no window hardcoded so "rolling" can be applied at the query layer. Confirm `Problem_Date` (vs. `Entered_Date`) is the right TAT start, and whether this covers the GSheet portion of the manual report at all — that layer wasn't investigated. |
| Monthly TAT Report | NetSuite + GSheet | ✅ Deployed, best-criteria — needs data-scientist input | Same build as Rolling TAT above — the view also exposes a `closed_month` column for calendar-month grouping. Same GSheet-coverage caveat applies. |
| Vox \| RUSH Open Sos | NetSuite | ✅ Built 2026-08-21, unblocked by screenshots | Reconsidered after seeing the real search criteria ("ATL \| RUSH Open SOs"): not a `Sales_v_Priority` lookup (that lead was a dead end, 0 rows live) — it's a `Memo (Main) contains RUSH` text filter, confirmed by a real order's Memo. Built as `sales_orders_rush_open_report` (`sales_orders.yaml`), filtering `UPPER(Sales_v_PO.Note) LIKE '%RUSH%'`. See `reports-list/sales.md` (same report, listed there as "One for Rush orders") and the SQL file header for the remaining "Billed" status gap and unconfirmed Note-field convention caveat. |
| **Labeling l Open WO: Results** | NetSuite | ✅ **Rebuilt Plex-native** | Reconsidered 2026-08-11 after seeing its actual NetSuite criteria (Type=Work Order, Status IN Released/In Process, Item:Class=Labeling) — the underlying question ("which jobs are open and need labeling") maps directly to Plex's own Job/Job_Op + Workcenter data. Built as `labeling_open_work_orders_report`, a 3rd `bq_view` on the existing `work_orders` pipeline — no NetSuite access needed at all. See below and `reports/sql/labeling_open_work_orders_view.sql`. |
| Printing Open Work Orders | NetSuite | ✅ Built | Listed on `reports-list/sales.md` (not this tab), but conceptually a Production report — same pattern as Labeling above, workcenter `'Printing%'`. Built as `printing_open_work_orders_report`, 4th `bq_view` on `work_orders.yaml`. |

## "Labeling | Open WO: Results" — reconsidered, not out of scope

Initially marked NetSuite-native and out of scope. A screenshot of the
actual saved-search criteria changed that: `Type = Work Order`,
`Status IN (Released, In Process)`, `Main Line = true`, `Item:Name NOT
CONTAINS 'lot traced'`, `Item:Class = Labeling`. The business question
underneath — "which jobs are open and need labeling" — doesn't require
NetSuite at all; Plex already tracks job status and workcenter assignment
independently.

**What made this buildable:** querying the `raw_Part_v_Workcenter` and
`raw_Part_v_Job_Status` tables already sitting in BigQuery from earlier
test runs (no new Plex query needed) surfaced the **full live workcenter
roster** for this tenant — confirming names that were previously only
tree-guessed or partially seen:

`Blend 2-5` (Batch), `Bottling Line 1-6` (Primary), `Bulk Room` (Primary),
`Encapsulation 1-10` (Primary), `First 48 #1` (Primary), `Label Approval` /
`Label Design` (Simplified — artwork approval, a *different* step from
physical labeling), `Labeling Line 1-6` (Primary), `Liquid Line`
(Primary), `Manufacture Rework` (Batch), `Powder Line` (Simplified),
`Pre-Weigh Planning` / `Preweigh 1-3` (Batch), `Printing` (Primary), `Roll
Compaction` (Batch).

And confirmed `Job_Status` values: `New`, `Production`, `Completed`,
`Hold`, `Cancelled`, `Scheduled` — each with proper
`Completed_Status`/`Cancelled_Status`/`Hold_Status` boolean flags, so
"open" can be expressed as the inverse of those three rather than a
brittle text match.

**This resolves the previously-flagged gap** in
`spreadsheets/mfg_job_schedule.md` and `spreadsheets/plex_production_yield_reference.md`
("Encap-style workcenter naming has zero live evidence") — see those docs'
updated notes.

**What's still an open gap, not guessed:** NetSuite's `Item:Name NOT
CONTAINS 'lot traced'` exclusion has no confirmed Plex equivalent and was
deliberately left out of the SQL rather than approximated. The
Released/In-Process → Scheduled/Production status mapping is inferred by
concept, not NetSuite-confirmed.

## Overall Production Yield verdict

See `spreadsheets/plex_production_yield_reference.md` for the full
analysis. Short version: the "Plex Report Equiv" column's claim that
Production Yield (ActionKey 7346) covers these 4 Daily Reports doesn't
hold up once the real templates are compared — Production Yield is a
per-container weighing/variance report, these are daily per-line
goal-vs-actual output logs with operator/attendance tracking that
Production Yield has no analog for at all. A better (still unconfirmed)
lead for the "Actual" output number is aggregating `Part_v_Job_Op`/
`Part_v_Cell_Production.Quantity` by date + workcenter.
