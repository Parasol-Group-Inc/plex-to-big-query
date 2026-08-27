# Weekly Production Update

> **Status:** ✅ Built and deployed 2026-08-26 (partial — see Flags below), verified live · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

For each of 4 departments (Encap, Bottling, Labeling, Printing): how much has actually been produced so far this week and this month. Also tells you how far into the current month you are, as a plain percentage.

## Where it fits

Partial coverage of the **Weekly Production Update** Google Sheet's "Goals" tab, tracked in [`spreadsheets/weekly_production_update.md`](../../spreadsheets/weekly_production_update.md). Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Same source and convention as the 4 Daily Reports (Encap/Blending/Labeling/Packaging): non-rejected quantity from Plex's production log, grouped by workcenter department. The only difference here is the aggregation window — week-to-date (Monday of the current week through today) and month-to-date (1st of the month through today) sums, instead of one row per single day — and this is the first report to cover the Printing department.

- **Pipeline:** `reports/work_orders.yaml` → `weekly_production_update_report`
- **SQL:** `reports/sql/weekly_production_update_view.sql`

## Flags and open questions

- **Only the Actual side is built.** The sheet's Goal figures (weekly/monthly targets per department) have no Plex source at all — they're numbers a person types in. Emilio's call 2026-08-26: keep computing "% of Goal" manually in the sheet rather than stand up a separate place for this pipeline to read targets from. If that changes, this report can join to a goal-reference table later without any rework on the Actual side.
- **The Capacity tab (Weekly/Monthly Capacity Avg %) is not built at all.** No confirmed formula or theoretical-capacity input exists yet — only Encap has real values filled in on the sheet itself, the other 3 departments are blank there too. Genuinely open, not guessed at.
- **The "Weekly Loss (Encap)" side table (Caps Lost / Time hours) is not built.** Caps Lost has the same confirmed source as the existing Daily Reports' scrap quantity, but it isn't part of this report's own Actual/Goal table and wasn't added separately. Lost time has no confirmed Plex source at all.
- **"WTD" is assumed to mean Monday-of-this-week-through-today** — Emilio's call 2026-08-26 — not a literal "Monday through Thursday" reading of the sheet's own "(M-T)" label.
- **Currently 0 rows of real activity for all 4 departments** — expected, not broken, for the same reason as every other production report on this tenant: very little real production has been logged yet.

## More detail

[`spreadsheets/weekly_production_update.md`](../../spreadsheets/weekly_production_update.md) has the full column-by-column mapping and the 4 open questions raised for Emilio.
