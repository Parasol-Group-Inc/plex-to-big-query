# Labeling Daily Report

- **Link:** https://docs.google.com/spreadsheets/d/1gVZe3_8wbexYIiQNtYdtCCvsJqUgj7zXrdTzVXl8XLI/edit
- **Type:** Google Sheet
- **Category:** Daily Numbers Report
- **Departments:** Production, Planning
- **Status:** 🔍 Mapped — template structure analyzed, not yet built
- **Plex reference:** [Production Yield](plex_production_yield_reference.md) (Inventory Tracking, ActionKey 7346) — **weak fit, see verdict below**

## What it is

`Labeling Daily Report - Template.csv`: a grid of dates × lines (Line 1–6,
"Line 3 Bottling", "Line 4 Bottling", "Blank & Tables"). Each line block has
Front/End counters, Start Up Time, three shift-checkpoint timestamps
(6:30 AM / 8:45 AM / 12:15 PM), Planned projected, Actual, Additional Notes.
Bottom rollup: Daily Projection/Total, Actual vs Projected %, Call Outs,
OFF, # Of Orders Complete, Cap/Day.

Same daily goal-vs-actual-per-line shape as
[Packaging Daily Report](packaging_daily_report.md), with shift checkpoints
instead of a single Start Up Time.

## Production Yield fit — weak

Same verdict as Packaging — see
[plex_production_yield_reference.md](plex_production_yield_reference.md).
No operator/shift-checkpoint concept on Production Yield; it's a
per-container weighing report, not a per-line labeling-count log.

## Better lead (unconfirmed)

Same as Packaging: `Part_v_Job_Op`/`Part_v_Cell_Production.Quantity`
aggregated by date + workcenter is a more plausible source for "Actual"
than Production Yield. The three shift-checkpoint timestamps and "# Of
Orders Complete" have no obvious Plex analog identified yet.

**Update 2026-08-11:** `Labeling Line 1` through `Labeling Line 6` are now
confirmed live workcenter names (see `reports-list/production.md`) — a
direct match to this sheet's own "Line 1–6" numbering, better than
Packaging's mismatch. This same workcenter set is already used by
`labeling_open_work_orders_report` (a Plex-native rebuild of NetSuite's
"Labeling | Open WO: Results"), which counts open jobs per Labeling Line —
"# Of Orders Complete" here is conceptually the closed-job counterpart of
that same query. Worth checking directly once real (non-template) data
exists.

## What's needed next

Real (non-template) data to confirm any correlation before building.
