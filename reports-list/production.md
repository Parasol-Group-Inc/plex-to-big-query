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
| Rolling TAT Report | NetSuite + GSheet | ❌ Out of scope (hybrid) | Turn-around-time reporting, NetSuite-primary. The GSheet portion is unclear from this row alone — would need its own investigation if ever prioritized |
| Monthly TAT Report | NetSuite + GSheet | ❌ Out of scope (hybrid) | Same as above; used for bonuses per the Function column |
| Vox \| RUSH Open Sos | NetSuite | ❌ Out of scope | Native NetSuite report, no Google Sheet layer |
| Labeling l Open WO: Results | NetSuite | ❌ Out of scope | Native NetSuite saved search |

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
