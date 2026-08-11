# Blending Daily Report

- **Link:** https://docs.google.com/spreadsheets/d/1NyJOe2PUyNElJkHz1kYknGGQC8fKaFd9l32nPFJJjNQ/edit
- **Type:** Google Sheet
- **Category:** Daily Numbers Report / Scheduling
- **Departments:** Production, Planning
- **Status:** 🔍 Mapped — template structure analyzed, not yet built
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

## What's needed next

Real (non-template) data to confirm any correlation before building.
