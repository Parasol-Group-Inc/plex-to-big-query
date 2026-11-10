# Production records (current)

> **Status:** ✅ Built 2026-11-06, created by hand in PlexProd and PlexTest · **Category:** Production (a building block, not a report people open) · **Runs:** rides the Work Orders pipeline (first view in `reports/work_orders.yaml`)

## What this tells you

Every production record Plex holds: what was made, on which job, workcenter and shift, by whom, when, how much, and whether it was rejected. It is the same list as Plex's `Part_v_Production` table, with one difference: while Plex's data link (ODBC) is frozen, it also includes the production Plex has recorded since, read from Plex's own screens every hour.

## Where it fits

Every report that counts production reads this instead of the raw table: the Blending, Encapsulating, Labeling and Packaging daily reports, Weekly Production Update, Production by Work Center Group (and so the scorecard's Production vs Goal tile), First Pass Yield by area, the MFG Job Schedule success metrics and Approaching MSL's usage figures.

## How it's built (high level)

- **Normally:** exactly `raw_Part_v_Production`.
- **While ODBC is frozen (PlexProd only):** the screen records in `PlexProd.live_production` (Plex's Job Production report plus Production History, see [PLEX_SCREEN_EXTRACTION.md](../PLEX_SCREEN_EXTRACTION.md)), plus every ODBC record the screens don't have. The `data_source` column says which (`live` or `odbc`).
- It goes back to ODBC alone by itself once ODBC has been stable for 6 hours and holds every screen record more than 3 hours old. Nobody has to switch it.
- Screen records get Plex's internal keys from the master tables: job operation by job + op number, part by part number + revision, workcenter by code, employee by full name.

- **Pipeline:** `reports/work_orders.yaml` → `part_production_current`
- **SQL:** `reports/sql/part_production_current_view.sql`

## Flags and open questions

- **Checked 2026-11-06:** on the 2,100 records both held (11-02, 11-03), the screens matched ODBC on every job operation, part, workcenter, employee, rejected flag, quantity and time.
- **Gap: jobs created after ODBC froze.** Their records have no job operation key (232 of 4,828 on 11-06), so reports that look up the job operation (the daily reports, FPY, weekly, job schedule metrics) don't count them. Production by Work Center Group and Approaching MSL do.
- Weights, production value and a few internal fields are blank on screen records; serial number is blank on a few. No report uses them.

## Where the data came from

*Added 2026-11-10.* Every row carries three columns that say where its data came from and how current it was:

| Column | Meaning |
|---|---|
| `data_source` | `odbc` (Plex's database feed, the normal case) or `live` (read from Plex's own screens because the database feed was behind) |
| `data_as_of` | for `odbc`, the newest change the feed had delivered; for `live`, when the screens were read |
| `data_label` | the two in words, e.g. "ODBC, loaded 11-10 13:01, newest change 11-10 11:56 MT" or "Plex screens, read 11-10 13:20 MT" |

They come from `PlexOps.data_freshness`, group **production**. Production always reads ODBC: the screens check (every 4 h) covers Label Design, revenue and shipments only. An old `data_as_of` on a working day means the feed has stopped, even if every run succeeded (as on 2026-11-10). See [data_freshness.md](data_freshness.md).

