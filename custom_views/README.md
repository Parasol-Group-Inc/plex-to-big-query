# Custom views (built by hand, outside the ETL)

BigQuery datasets that people build in the console, not the ETL. The ETL never recreates
or reverts them, and until 2026-11-11 none of them were in git. Backed up after the
11-11 meeting with Jennilyn.

| Dataset | What it is | Backup |
| --- | --- | --- |
| [`VoxScorecardsLive`](VoxScorecardsLive/README.md) | Jennilyn's views over PlexProd for the Vox scorecards and day-to-day questions: WIP status, sales order aging, rush orders, scrap MTD, expiring inventory, MSL with held stock. Also older NetSuite and Monday-fed tables. 60 views, 25 tables. | SQL and docs here; the 25 tables' data copied to `Backups.VoxScorecardsLive__<table>_20261111` (no expiry) |

## How to refresh

```bash
python scripts/backup_custom_views.py VoxScorecardsLive
git diff custom_views/
```

The diff shows what changed since the last backup.

The data of the tables is a separate copy. Re-copy it for a new date with `bq cp`, as the
operator, into `Backups.VoxScorecardsLive__<table>_<YYYYMMDD>`.

## What is not here

- **11 tables have no SQL**, only their columns (`.schema.json`). Another process loads them, or
  they were built before the 180 days of job history. Several of them changed today (for example
  `SalesDB_YTD` and the `new_*_<id>` tables), so something outside this repo fills them.
- **`plex_mirror`** is also Jennilyn's. It has 94 objects, and she writes to `pb_requests` and
  `pb_reserved_numbers`. It is not backed up yet: run the script with `plex_mirror` when wanted.
