# Packaging Daily Report

- **Link:** https://docs.google.com/spreadsheets/d/14Qazm-rH26O66BLcnVZi5GahsPQ-TL5P2WLlSG6eFJc/edit
- **Type:** Google Sheet
- **Category:** Daily Numbers Report
- **Departments:** Production, Planning
- **Status:** ✅ Deployed to test 2026-08-21 (Actual half only), 0 rows, decided Bottling mapping — `packaging_daily_report` (`reports/work_orders.yaml`)
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

## Built 2026-08-21 — resolved the workcenter-group question

This was the hardest of the 4 to place: a Plex UI screenshot of the
Workcenter Group pick list confirmed **"Packaging" is not a Plex
workcenter group at all** — the confirmed live groups are Blending,
Bottling, Encapsulating, Labeling, Pre-Weigh, Preparation, Printing,
Rework, Scheduling. "Packaging" only exists in Plex as a Department code
(`PACK`) and a separate `Part_Group` value, neither of which is
workcenter-shaped. Built on `Workcenter_Group = 'Bottling'` instead, since
that roster (`Bottling Line 1`-`6`, `Bulk Room`, `Powder Line`,
`Liquid Line`) matches this sheet's own line names almost exactly. Built
as `packaging_daily_report`, aggregating `Part_v_Cell_Production.Quantity`
by production date + workcenter (`reports/sql/packaging_daily_report_view.sql`).

## Corrected same day: rebuilt on `Part_v_Production`

Same correction as `encap_daily_report.md` — a live "Job Production" UI
report screenshot showed `Part_v_Production` (with Employee/Shift/Rejected
columns) is the right table, not `Part_v_Cell_Production`. Rebuilt, now
also exposes `employee_count`/`employees` and `scrap_qty`.

## Test deploy result 2026-08-21 (post-correction)

View creates cleanly, still **0 rows** — benign: none of this tenant's
real jobs have run yet (see `encap_daily_report.md` for the full finding).

## What's needed next

Recheck once this tenant's jobs actually move past `Scheduled`. Then a
filled-in week or month of this sheet to confirm whether "Actual" numbers
correlate with `Part_v_Production` quantities, and whether the sheet's
"Line" numbering lines up 1:1 with `Bottling Line N` or needs remapping.
