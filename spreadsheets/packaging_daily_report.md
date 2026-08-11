# Packaging Daily Report

- **Link:** https://docs.google.com/spreadsheets/d/14Qazm-rH26O66BLcnVZi5GahsPQ-TL5P2WLlSG6eFJc/edit
- **Type:** Google Sheet
- **Category:** Daily Numbers Report
- **Departments:** Production, Planning
- **Status:** 🔍 Mapped — template structure analyzed, not yet built
- **Plex reference:** [Production Yield](plex_production_yield_reference.md) (Inventory Tracking, ActionKey 7346) — **weak fit, see verdict below**

## What it is

`Packaging Daily Report - Template.csv`: a grid of dates (columns) ×
production lines (Line 1–5, Bulk, Gummy Line/Line 6, Powder Line, Liquid
Line). Each line block has Front/Mid/End counters, Start Up Time, Planned
projected, Actual, Real Capacity. Bottom rollup: Daily Projection, Daily
Total, Actual vs Projected %, Cap total Real, Call Outs, OFF.

This is a **daily goal-vs-actual output log per packaging line**, not a
job/part-level tracker like MFG Job Schedule.

## Production Yield fit — weak

Bottle/label counts, not weights — "Tips Tails"/"Coil"/"Heat No" on
Production Yield read as raw-material-coil or ingredient weigh-out
concepts, not finished-good packaging counts. No `Operator`, no
`Start Up Time`, no attendance concept on Production Yield at all — see
[plex_production_yield_reference.md](plex_production_yield_reference.md)
for the full verdict across all 4 Daily Reports.

## Better lead (unconfirmed)

The "Actual" per-line daily count is more plausibly `Part_v_Job_Op.Quantity`
or `Part_v_Cell_Production.Quantity`, aggregated by `Complete_Date` +
`Workcenter_Key` — data already extracted by this project's existing
pipelines. "Planned projected," "Start Up Time," "Real Capacity," and the
employee Call Outs/OFF roster look like genuinely manual/scheduling inputs
with no Plex analog — same category as MFG Job Schedule's manual-only
columns.

**Update 2026-08-11:** the workcenters this sheet's "Lines" plausibly map
to are now confirmed live — `Bottling Line 1` through `Bottling Line 6`,
plus `Liquid Line`, `Powder Line`, `Bulk Room` (see
`reports-list/production.md`). The sheet's own "Line" numbering
(1–5/Bulk/Gummy Line-6/Powder Line/Liquid Line) doesn't map 1:1 to
`Bottling Line N` — needs real filled-in data to confirm which sheet
"Line" corresponds to which Plex workcenter before aggregating anything.

## What's needed next

Real (non-template) data — a filled-in week or month of this sheet — to
confirm whether "Actual" numbers actually correlate with Job_Op/Cell
Production quantities before building anything.
