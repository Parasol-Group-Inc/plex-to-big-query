# Blending Daily Report

- **Link:** https://docs.google.com/spreadsheets/d/1NyJOe2PUyNElJkHz1kYknGGQC8fKaFd9l32nPFJJjNQ/edit
- **Type:** Google Sheet
- **Category:** Daily Numbers Report / Scheduling
- **Departments:** Production, Planning
- **Status:** ✅ Deployed to test 2026-08-21 (Actual half only), 0 rows — `blending_daily_report` (`reports/work_orders.yaml`)
- **Plex reference:** [Production Yield](plex_production_yield_reference.md) (Inventory Tracking, ActionKey 7346) — **weakest-but-most-plausible fit of the 4 Daily Reports, see verdict below**

## What it is

`Blending Daily Report - Template.csv`: a grid of dates × stations
(Pre-Weigh 1/2/3, Blending 2/3/4 (1500L)/5). Each station block has 2
Operator slots, Start Up Time, Planned projected, Actual, Additional Notes.
Bottom rollup: Daily Weigh-Out Goal/Total, Daily Blending Goal/Total,
Actual vs Projected %, Call Outs, OFF, per-station Capacity %, and a named
employee roster with call-out tracking.

Confirms real workcenter naming ("Blending 2", "Blending 4 (1500L)") that
matches [mfg_job_schedule.md](mfg_job_schedule.md)'s live-confirmed
`Workcenter.Name` finding (`'Blend 2'`, `Workcenter_Type = 'Batch'`) — same
naming family, good independent confirmation.

## Production Yield fit — weakest-but-most-plausible

The only one of the 4 Daily Reports with a genuine weighing workflow
("Pre-Weigh" stations, "Daily Weigh-Out Goal/Total") — Production Yield is
also weight-centric, so this is the closest conceptual overlap of the four.
Still unconfirmed, and still missing the operator/attendance half entirely.
See [plex_production_yield_reference.md](plex_production_yield_reference.md)
for the full cross-sheet verdict.

## Better lead (unconfirmed)

`Part_v_Job_Op`/`Part_v_Cell_Production.Quantity` aggregated by date +
workcenter, same as the other 3 Daily Reports — plus, given the confirmed
"Blend N" workcenter naming, this is the sheet where a
Blending-vs-Encapsulation workcenter classification (flagged as a gap in
[mfg_job_schedule.md](mfg_job_schedule.md)) would matter most.

**Update 2026-08-11:** the gap is now resolved — `Blend 2` through `Blend
5` AND `Preweigh 1` through `Preweigh 3` (plus `Pre-Weigh Planning`) are
all confirmed live `Workcenter_Type = 'Batch'` (see
`reports-list/production.md`), matching this sheet's "Pre-Weigh 1/2/3" and
"Blending 2/3/4/5" sections almost exactly.

## Built 2026-08-21

Same unblock as the other 3 Daily Reports (Plex's own "Daily Shifts" UI
report confirms the rollup exists natively). Built as `blending_daily_report`,
aggregating `Part_v_Cell_Production.Quantity` by production date +
workcenter, filtered to `Workcenter_Group IN ('Blending', 'Pre-Weigh')`
since the sheet's grid needs both station types
(`reports/sql/blending_daily_report_view.sql`). Weigh-out vs. blending
quantities aren't split — both workcenter groups' `Cell_Production` rows
land in one `actual_qty` column; only the "Actual" quantity is built at
all, not Planned/attendance.

## Corrected same day: rebuilt on `Part_v_Production`

Same correction as `encap_daily_report.md` — a live "Job Production" UI
report screenshot showed `Part_v_Production` (with Employee/Shift/Rejected
columns) is the right table, not `Part_v_Cell_Production`. Rebuilt, now
also exposes `employee_count`/`employees` and `scrap_qty`.

## Test deploy result 2026-08-21 (post-correction)

View creates cleanly, still **0 rows** — benign: none of this tenant's
real jobs have run yet (see `encap_daily_report.md` for the full finding).

## What's needed next

Recheck once this tenant's jobs actually move past `Scheduled`. Then
confirm `Part_v_Production` correlates with this sheet's actual weigh-out/
blending totals, and whether Weigh-Out and Blending goals need to be split
into separate columns once real data shows they're tracked differently.
