# Data freshness (`PlexOps.data_freshness`)

**What it answers:** for each report group, are the reports reading Plex's database feed (ODBC) or Plex's own screens right now, and how current is that data?

**Added 2026-11-10**, after the feed served data frozen at 08:10 MT for 4.5 hours while every run reported success. A dashboard can show this view as a banner.

## Columns

One row per dataset (`PlexProd`, `PlexTest`) and report group.

| Column | Meaning |
|---|---|
| `report_group` | `label_design`, `revenue` (revenue and shipments) or `production` |
| `data_source` | `odbc` or `live` (Plex screens) |
| `data_as_of` | ODBC: the newest change delivered into BigQuery (order update, shipper or invoice, production record); live: when the screens were read |
| `data_label` | the two in words, e.g. "ODBC, loaded 11-10 13:01, newest change 11-10 11:56 MT" |
| `odbc_data_as_of`, `screens_read_at` | both times, whichever is in use |
| `odbc_lag_min` | how far ODBC was behind the screens at the last check (every 4 h) |
| `latest_verdicts`, `last_check_at` | the last screens check per screen |

## How the source is chosen

`live` only in PlexProd, only for Label Design and revenue, and only while the screens check (`plex-live-screens`, every 4 h) has found ODBC behind or disagreeing (`PlexOps.live_source`) **and** the screens were read in the last 5 hours. Production always reads ODBC. This is the same rule the reports use, so the label always matches the data.

## Which reports carry it

Every report built on `label_design_report`, `shipping_revenue_report` or `part_production_current` has `data_source`, `data_as_of` and `data_label` columns from this view (17 reports; each report's doc has a "Where the data came from" section). The Label Design push writes `data_label` into the "Data Source" text column on the Plex Import Test and Design & QA boards.

Defined in `terraform/main.tf` (`google_bigquery_table.data_freshness`). Runbook: `docs/PLEX_SCREEN_EXTRACTION.md`, "Reconciliation (cloud job)".
