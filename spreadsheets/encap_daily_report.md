# Encap Daily Report

- **Link:** https://docs.google.com/spreadsheets/d/105iiQ_fFqNRg_6hpP0nI5CreuKeKL35bk2piIO2Gd5c/edit
- **Type:** Google Sheet
- **Category:** Encap Scheduling / Planning
- **Departments:** Production, Planning
- **Status:** 🔍 Mapped — template structure analyzed, not yet built
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

## What's needed next

Real (non-template) data, and ideally the actual Encap workcenter names
from a live Plex query, before building.
