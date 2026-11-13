# Weekly Production Update

> **Status:** ✅ Built and deployed 2026-08-26 (partial — see Flags below), verified live · **Category:** Production · **Runs:** rides the Work Orders pipeline, prod 1 PM / 6 PM / 11 PM probe + 4 AM full (`PlexOps.etl_schedule`), test nightly

## What this tells you

For each of 4 departments (Encap, Bottling, Labeling, Printing): how much has actually been produced so far this week and this month. Also tells you how far into the current month you are, as a plain percentage.

## Where it fits

Partial coverage of the **Weekly Production Update** Google Sheet's "Goals" tab, tracked in [`spreadsheets/weekly_production_update.md`](../../spreadsheets/weekly_production_update.md). Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Same source and convention as the 4 Daily Reports (Encap/Blending/Labeling/Packaging): non-rejected quantity from Plex's production log, grouped by workcenter department. The only difference here is the aggregation window — week-to-date (Monday of the current week through today) and month-to-date (1st of the month through today) sums, instead of one row per single day — and this is the first report to cover the Printing department.

- **Pipeline:** `reports/work_orders.yaml` → `weekly_production_update_report`
- **SQL:** `reports/sql/weekly_production_update_view.sql`

## Flags and open questions

- **Added 2026-11-06: counts Plex's production screens while ODBC is frozen.** It now reads `part_production_current` instead of `raw_Part_v_Production`: the same records, plus, in PlexProd, the production Plex has recorded since ODBC froze (11-04), loaded hourly from Plex's own screens (see [PLEX_SCREEN_EXTRACTION.md](../PLEX_SCREEN_EXTRACTION.md)). It returns to ODBC alone by itself once ODBC is stable and caught up. On 11-02 and 11-03 the screens matched ODBC on every record. Gap: records on jobs created after the freeze are missing where this report needs the job operation.
- **Bottling 9-parts are not counted (Jennilyn, 2026-10-22).** When Bottling completes a job for a part starting with **9** (the finished-good version), the same output was already counted on the job for its **5** part, so counting both is double credit. Bottling production records for 9-parts are left out, good and scrap alike. **Bottling only:** Labeling's output is all 9-parts and still counts. On 2026-10-22 it removes the 14,055 Slim Complex FG units (`93323-10REDRO-0`, recorded that day) from Bottling's week and month to date; they were already counted on the 5 part `53323-10REDRO-0`. **Bulk cases (`9xxxx-BK…`) are exempt and still count** (Jennilyn, 2026-10-22): they have no 5-part job.
- **From 1 Nov 2026, Bottling 9-parts count (Jennilyn, 2026-10-30).** The drop above applies only before 1 Nov. New columns `mtd_bottling_9part_qty` and `mtd_bottling_9part_with_5_bom_qty` (possible double credit; should be 0 once her BOM changes are complete).
- **From 13 Nov 2026, the 5/9 parts are dropped again (Jennilyn, 2026-11-13).** "If we can drop those it'd be great. There are only 5 active parts currently in the system that we are still using with this 5/9 double count setup. We are still phasing these out." A Bottling record for a 9-part is left out, at any date, while that 9-part still has an active BOM line to a 5-part: the output was already counted on the 5-part's job. In November to 13 Nov that was 11,500 units on 3 parts (93147-10VOXNU-0, 93055-45VOXNU-0, 93334-01VOXNU-0), each with its 5-part bottled the same week. `mtd_bottling_9part_with_5_bom_qty` now shows the quantity left out (it is not in the totals). The rule reads today's BOM, so when Jennilyn removes a part's 5-part BOM, that part's earlier records count again (OPEN_ITEMS D27).
- **Fixed 13 Nov 2026: production records were missing.** The report found each record's department through its job operation, and that lookup finds nothing for records whose operation is not in the extract, so those records were silently left out. In November to 13 Nov that was 2,575 records: Labeling 283,763 units, Printing 12,701, Bottling 2,501 (MTD Labeling read 41,093 instead of 324,206). It now uses the workcenter on the production record itself, as the monthly report always has, and its month-to-date totals match the monthly report exactly. Found by the 12 Nov numbers audit.
- **Only the Actual side is built.** The sheet's Goal figures (weekly/monthly targets per department) have no Plex source at all — they're numbers a person types in. Emilio's call 2026-08-26: keep computing "% of Goal" manually in the sheet rather than stand up a separate place for this pipeline to read targets from. If that changes, this report can join to a goal-reference table later without any rework on the Actual side.
- **The Capacity tab (Weekly/Monthly Capacity Avg %) is not built at all.** No confirmed formula or theoretical-capacity input exists yet — only Encap has real values filled in on the sheet itself, the other 3 departments are blank there too. Genuinely open, not guessed at.
- **The "Weekly Loss (Encap)" side table (Caps Lost / Time hours) is not built.** Caps Lost has the same confirmed source as the existing Daily Reports' scrap quantity, but it isn't part of this report's own Actual/Goal table and wasn't added separately. Lost time has no confirmed Plex source at all.
- **"WTD" is assumed to mean Monday-of-this-week-through-today** — Emilio's call 2026-08-26 — not a literal "Monday through Thursday" reading of the sheet's own "(M-T)" label.
- **Currently 0 rows of real activity for all 4 departments** — expected, not broken, for the same reason as every other production report on this tenant: very little real production has been logged yet.

## More detail

[`spreadsheets/weekly_production_update.md`](../../spreadsheets/weekly_production_update.md) has the full column-by-column mapping and the 4 open questions raised for Emilio.

## Where the data came from

*Added 2026-11-10.* Every row carries three columns that say where its data came from and how current it was:

| Column | Meaning |
|---|---|
| `data_source` | `odbc` (Plex's database feed, the normal case) or `live` (read from Plex's own screens because the database feed was behind) |
| `data_as_of` | for `odbc`, the newest change the feed had delivered; for `live`, when the screens were read |
| `data_label` | the two in words, e.g. "ODBC, loaded 11-10 13:01, newest change 11-10 11:56 MT" or "Plex screens, read 11-10 13:20 MT" |

They come from `PlexOps.data_freshness`, group **production**. Production always reads ODBC: the screens check (every 4 h) covers Label Design, revenue and shipments only. An old `data_as_of` on a working day means the feed has stopped, even if every run succeeded (as on 2026-11-10). See [data_freshness.md](data_freshness.md).

