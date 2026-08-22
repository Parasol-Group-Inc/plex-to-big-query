# Reports List — Production

Source file: `Reports List - Production.csv`. Columns: Report Name,
Source, Function, Users, Link, Priority, Plex Report Equiv.

This tab has the heaviest overlap with [`spreadsheets/`](../spreadsheets/) —
most rows here already have (or now have) their own detail doc there.

| Report | Source | Status | Notes |
|---|---|---|---|
| MFG Job Schedule | Google Sheet | ✅ Already built | See `spreadsheets/mfg_job_schedule.md` |
| Encap Daily Report | Google Sheet | ✅ Deployed to test 2026-08-21 (Actual half only), 0 rows | Built as `encap_daily_report` (`work_orders.yaml`) on `Part_v_Cell_Production`, filtered `Workcenter_Group = 'Encapsulating'`. Deploys cleanly; 0 rows because `Part_v_Cell_Production` is empty tenant-wide (see verdict below). Planned Hours/attendance/scrap not built — no Plex analog found, same as MFG Job Schedule's manual-only columns. See `spreadsheets/encap_daily_report.md`. |
| Packaging Daily Report | Google Sheet | ✅ Deployed to test 2026-08-21 (Actual half only), 0 rows, decided Bottling mapping | Built as `packaging_daily_report`, filtered `Workcenter_Group = 'Bottling'` — "Packaging" isn't a Plex workcenter group at all (it's a Department code and a separate Part_Group), but the sheet's own lines match the Bottling roster almost exactly. See `spreadsheets/packaging_daily_report.md`. |
| Labeling Daily Report | Google Sheet | ✅ Deployed to test 2026-08-21 (Actual half only), 0 rows | Built as `labeling_daily_report`, filtered `Workcenter_Group = 'Labeling'` — direct match to the sheet's own Line 1-6 numbering. See `spreadsheets/labeling_daily_report.md`. |
| Blending Daily Report | Google Sheet | ✅ Deployed to test 2026-08-21 (Actual half only), 0 rows | Built as `blending_daily_report`, filtered `Workcenter_Group IN ('Blending', 'Pre-Weigh')` (the sheet's grid needs both). See `spreadsheets/blending_daily_report.md`. |
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

**Update 2026-08-21 — that lead is now much stronger, not just
unconfirmed.** A screenshot of Plex's own "Daily Shifts" UI report shows
exactly this rollup already exists natively: grouped by
Manager/Department/Workcenter/Part/date, with **Planned Production Hours,
Parts Produced, Parts Scrapped, Scrap Rate, Earned/Actual Machine Hours,
Efficiency, Utilization, OEE, Earned/Actual Labor Hours, Labor
Efficiency** — i.e. exactly the goal-vs-actual-output-plus-attendance shape
these 4 reports need, that Production Yield never had. Structural
evidence this is buildable from confirmed-live views: `Part_v_Job_Op` +
`Part_v_Cell_Production` (Quantity, Production_Date, Job_Op_Key — schema
confirmed) + `Part_v_Workcenter` (`Workcenter_Group`/`Department_No`,
already extracted but unused) + `Common_v_Department` (not yet extracted).
`Workcenter_Group` also gives a cleaner per-report filter than the
`wc.Name LIKE 'Labeling Line%'` text pattern already used elsewhere:
confirmed live groups are Blending, Bottling, Encapsulating, Labeling,
Pre-Weigh, Preparation, Printing, Rework, Scheduling — which maps cleanly
to Blending/Labeling/Bottling Daily Reports; Packaging has no matching
workcenter group of its own (it's a Department code `PACK` and a separate
`Part_Group` value instead) — **decided** to map it onto `Workcenter_Group
= 'Bottling'` since the sheet's own line names match that roster almost
exactly. See `catalog/plex_catalog_index.md`'s 2026-08-21 confirmed-values
section for the full column/value detail.

**Built 2026-08-21** — all 4 reports now have an `Actual`-quantity bq_view
(`encap_daily_report`, `blending_daily_report`, `labeling_daily_report`,
`packaging_daily_report`, all in `work_orders.yaml`), aggregating
`Part_v_Cell_Production.Quantity` by production date + workcenter within
each report's `Workcenter_Group` filter. Planned Hours, Start-Up/Stop
times, and the employee Call Outs/OFF attendance roster are deliberately
**not** built — no Plex analog identified, same treatment as MFG Job
Schedule's manual-only columns.

**Deployed to test 2026-08-21 — all 4 views create cleanly, but return 0
rows.** Not a code bug: `raw_Part_v_Cell_Production` came back with **0
rows from Plex**, despite `raw_Part_v_Job` having 16 real live jobs and
`raw_Part_v_Workcenter` having 38 real live workcenters on this tenant —
i.e. none of this tenant's real jobs have any Cell Production records at
all, at least in this test sample. This is a materially weaker signal than
"unconfirmed" — it raises a real question of whether this tenant uses
Plex's Cell Production tracking mode at all, versus whatever feeds the
Daily Shifts UI report's numbers by some other mechanism (e.g.
`Part_v_Workcenter_Log` hours combined with `Job_Op` quantities). **Needs
a direct answer from Vox/data-scientist: does this tenant track Cell
Production, and if not, what does?** Until then, these 4 views are
schema-correct and safely deployed, but should not be assumed to produce
real numbers once run against production data.
