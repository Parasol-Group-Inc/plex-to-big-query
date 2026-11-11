# Data freshness (`PlexOps.data_freshness`)

**What it answers:** for each report group, are the reports reading Plex's database feed (ODBC) or Plex's own screens right now, and how current is that data?

**Added 2026-11-10**, after the feed served data frozen at 08:10 MT for 4.5 hours while every run reported success. A dashboard can show this view as a banner.

## Columns

One row per dataset (`PlexProd`, `PlexTest`) and report group.

| Column | Meaning |
|---|---|
| `report_group` | `label_design`, `revenue` (revenue and shipments) or `production` |
| `data_source` | `odbc` or `live` (Plex screens). Label Design is `odbc` here; each of its rows says its own source |
| `data_as_of` | ODBC: the newest change delivered into BigQuery (order update, shipper or invoice, production record); live: when the screens were read |
| `data_label` | the two in words, e.g. "ODBC, loaded 11-10 13:01, newest change 11-10 11:56 MT" |
| `odbc_data_as_of`, `screens_read_at` | both times, whichever is in use |
| `odbc_lag_min` | how far ODBC was behind the screens at the last check (every 4 h) |
| `latest_verdicts`, `last_check_at` | the last screens check per screen |
| `screens_fill_in` | Label Design only: a screen read under 3 h old adds the lines ODBC lacks (since 2026-11-11) |

## How the source is chosen

Since 2026-11-11 (`docs/ODBC_VS_SCREENS.md`):

- **Label Design** combines the two sources. Its rows come from ODBC, plus the lines only
  the screens have, while a screen read is under 3 h old. In `label_design_report` each row
  says its own source: `data_source` = `live` with "Plex screens, read ...", or the ODBC
  label. Here the group label adds "; new lines from Plex screens, read ..." while such a
  read exists.
- **Revenue** never switches: shipments and revenue are not time critical.
- **Production** always reads ODBC.

## Which reports carry it

Every report built on `label_design_report`, `shipping_revenue_report` or `part_production_current` has `data_source`, `data_as_of` and `data_label` columns from this view (17 reports; each report's doc has a "Where the data came from" section). The Label Design push writes `data_label` into the "Data Source" text column on the Plex Import Test and Design & QA boards.

Defined in `terraform/main.tf` (`google_bigquery_table.data_freshness`). Runbook: `docs/PLEX_SCREEN_EXTRACTION.md`, "Reconciliation (cloud job)".
