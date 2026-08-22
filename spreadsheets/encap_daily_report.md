# Encap Daily Report

- **Link:** https://docs.google.com/spreadsheets/d/105iiQ_fFqNRg_6hpP0nI5CreuKeKL35bk2piIO2Gd5c/edit
- **Type:** Google Sheet
- **Category:** Encap Scheduling / Planning
- **Departments:** Production, Planning
- **Status:** ✅ Deployed to test 2026-08-21 (Actual half only), promoted to prod GCS config 2026-08-22, 0 rows — `encap_daily_report` (`reports/work_orders.yaml`)
- **Plex reference:** [Production Yield](plex_production_yield_reference.md) (Inventory Tracking, ActionKey 7346) — **worst fit of the 4 Daily Reports, see verdict below**

## What it is

`Encap Daily Report - Template.csv`: a grid of dates × encapsulation
stations (Encap 1/2/4/5/7/8/9/10). Each station block has Operator,
Product, Start Up Time, Stop Time, Planned projected, Actual, Additional
Notes. Bottom rollup: Daily Production Goal/Actual, Target vs Actual (+/-),
Actual vs Projected %, Capacity %.

Same daily goal-vs-actual-per-workcenter shape as the other 3 Daily
Reports, one column richer than Blending (explicit Stop Time in addition
to Start Up Time, and a `Product` field per station per day).

## Production Yield fit — worst of the 4

No weight concept anywhere in this template (capsule counts only), and
Production Yield is fundamentally weight-centric (Gross Part Weight, Tips
Tails Weight, Adjusted Coil Weight). See
[plex_production_yield_reference.md](plex_production_yield_reference.md)
for the full cross-sheet verdict — this is the sheet where "this works for
part of it" (per `Reports List - Production.csv`'s "Plex Report Equiv"
column) holds up least well.

## Better lead (unconfirmed)

Same as the others: `Part_v_Job_Op`/`Part_v_Cell_Production.Quantity`
aggregated by date + workcenter, filtered to encapsulation-type
workcenters — which is exactly the "Encap"-naming gap flagged in
[mfg_job_schedule.md](mfg_job_schedule.md) (blending workcenter names are
live-confirmed, "Encap"-style names are not yet). Confirming real Encap
workcenter names would resolve both gaps at once.

**Update 2026-08-11:** resolved — `Encapsulation 1` through `Encapsulation
10` (full word, not the sheet's abbreviated "Encap N") are confirmed live,
`Workcenter_Type = 'Primary'` (see `reports-list/production.md`). Note:
this template only has stations for 1, 2, 4, 5, 7, 8, 9, 10 (skipping 3 and
6) — worth confirming with real data whether those two are decommissioned,
renamed, or just not yet added to the sheet, rather than assuming either.

## Built 2026-08-21

Unblocked by a screenshot of Plex's own "Daily Shifts" UI report, which
confirmed this exact per-workcenter/per-date rollup exists natively. Built
as `encap_daily_report`, aggregating `Part_v_Cell_Production.Quantity` by
production date + workcenter, filtered to `Workcenter_Group =
'Encapsulating'` (see `reports/sql/encap_daily_report_view.sql`). Only the
"Actual" quantity is built — Planned/Start-Up-Stop/attendance columns have
no Plex analog and are not guessed at.

## Corrected same day: rebuilt on `Part_v_Production`

Initial deploy on `Part_v_Cell_Production` returned 0 rows. Live Plex
screenshots (Job Manager, Job Detail, Job Routing, Job Production report)
showed the real cause: all 16 real jobs on this tenant were freshly
created that same morning with 0 actual hours logged — a benign "nothing
has run yet," not a schema problem. That investigation also surfaced a
real correction: Plex's own "Job Production" UI report (columns including
**Employee** and **Shift**) matches `Part_v_Production` field-for-field,
not `Part_v_Cell_Production` (which has no Employee/Shift/Rejected columns
at all). Rebuilt on `Part_v_Production`, which also adds real
`employee_count`/`employees` and `scrap_qty` (via the `Rejected` flag) —
resolving 2 of this report's 3 "no Plex analog" gaps.

## Test deploy result 2026-08-21 (post-correction)

View creates cleanly, still **0 rows** — for the same benign reason:
`raw_Part_v_Production` is also empty, because none of this tenant's real
jobs have run yet.

## What's needed next

Recheck once this tenant's jobs actually move past `Scheduled` status.
Then confirm Encap stations 3 and 6 (skipped in the sheet's template) show
real activity or true zeros.
