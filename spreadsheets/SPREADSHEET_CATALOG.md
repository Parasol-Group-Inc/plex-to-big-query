# Spreadsheet → Plex/BigQuery Catalog

Hub for manually maintained spreadsheets that this pipeline is building
BigQuery reports for. Each row here is one spreadsheet; each has its own
detail doc in this folder with the full column-by-column mapping (what's
buildable from Plex, what's a gap, what's manual-only).

This is a different catalog from the other two in this repo:
- [`catalog/`](../catalog/) — raw Plex ODBC **views** (queryable, what
  `reports/*.yaml` extracts from)
- [`mapping/`](../mapping/) — Plex UI **report** screens and stored-procedure
  data sources (reference-only, not queryable — see
  [docs/PLEX_REPORTS_CATALOG.md](../docs/PLEX_REPORTS_CATALOG.md))
- `spreadsheets/` (this folder) — external, human-maintained Google Sheets
  that this project is turning into (or cross-referencing against) BigQuery
  reports
- [`reports-list/`](../reports-list/) — a wider, company-wide inventory of
  *every* report across departments regardless of source system (NetSuite,
  DataNinja, Monday.com, Excel, Google Sheets). Most rows there are out of
  scope for this pipeline; it's where new candidates for this folder get
  surfaced from

## Catalog

| Spreadsheet | Type | Category | Departments | Plex Reference | Status | Detail Doc |
|---|---|---|---|---|---|---|
| [MFG Job Schedule](https://docs.google.com/spreadsheets/d/1xqccqPwPA37291vJOpxNZhBGiyy_xbp4TPoW0UMyozA/edit) | Google Sheet | Product Release Tracking / Forecasting | Production, Supply Chain, Sales, Quality | — (built from raw ODBC views directly) | ✅ Built | [mfg_job_schedule.md](mfg_job_schedule.md) |
| [Bottling Job Schedule](https://docs.google.com/spreadsheets/d/1m6ZmBMBCQHTsc4S7W-FicIaE63AOfxvobbnEDRwmqAk/edit) | Google Sheet | Scheduling bottling jobs | Production, Planning, Sales | — (same views as MFG Job Schedule) | 🔍 Mapped | [bottling_job_schedule.md](bottling_job_schedule.md) |
| [Packaging Daily Report](https://docs.google.com/spreadsheets/d/14Qazm-rH26O66BLcnVZi5GahsPQ-TL5P2WLlSG6eFJc/edit) | Google Sheet | Daily Numbers Report | Production, Planning | Production Yield (Inventory Tracking, ActionKey 7346) — **weak fit** | 🔍 Mapped | [packaging_daily_report.md](packaging_daily_report.md) |
| [Labeling Daily Report](https://docs.google.com/spreadsheets/d/1gVZe3_8wbexYIiQNtYdtCCvsJqUgj7zXrdTzVXl8XLI/edit) | Google Sheet | Daily Numbers Report | Production, Planning | Production Yield (Inventory Tracking, ActionKey 7346) — **weak fit** | 🔍 Mapped | [labeling_daily_report.md](labeling_daily_report.md) |
| [Blending Daily Report](https://docs.google.com/spreadsheets/d/1NyJOe2PUyNElJkHz1kYknGGQC8fKaFd9l32nPFJJjNQ/edit) | Google Sheet | Daily Numbers Report / Scheduling | Production, Planning | Production Yield (Inventory Tracking, ActionKey 7346) — **weakest-but-most-plausible** | 🔍 Mapped | [blending_daily_report.md](blending_daily_report.md) |
| [Encap Daily Report](https://docs.google.com/spreadsheets/d/105iiQ_fFqNRg_6hpP0nI5CreuKeKL35bk2piIO2Gd5c/edit) | Google Sheet | Encap Scheduling / Planning | Production, Planning | Production Yield (Inventory Tracking, ActionKey 7346) — **worst fit** | 🔍 Mapped | [encap_daily_report.md](encap_daily_report.md) |

## Status legend

- ⏳ **Pending** — spreadsheet identified, not yet analyzed. Needs the
  actual sheet content (CSV export, screenshot, or shared access) before a
  column-by-column mapping can be done — a name/category/link alone isn't
  enough to know what to build.
- 🔍 **Mapped** — column-by-column mapping done (buildable / gap / manual
  split identified), report(s) not yet built.
- 🚧 **Building** — reports under construction / local-tested, not yet
  deployed.
- ✅ **Built** — deployed to GCP, verified against real BigQuery.

## Working pattern (established on MFG Job Schedule)

1. Get the spreadsheet's actual content (CSV export or full screenshot of
   every column) — a name and category aren't enough to map columns.
2. Map every column against the real Plex ODBC catalog (`catalog/*.md`),
   confirming live against `vox.test.odbc.plex.com` where a plausible view
   exists — never guess a column mapping from a view *name* alone.
3. Split columns into three buckets and be explicit about all three, not
   just the first: **buildable from Plex** (cite the exact view/column),
   **gap** (plausible source exists but needs confirmation, or no source
   exists at all), **manual-only** (human judgment/process fields that no
   ERP will ever have — don't fabricate a column for these).
4. Build BigQuery report(s) reusing existing extractions/pipelines where the
   grain already matches (see `mfg_job_schedule_report`'s design — added as
   a second `bq_view` on the existing `work_orders` pipeline rather than a
   parallel report) rather than defaulting to one new report per spreadsheet.
5. Test every view against real BigQuery (not just SQL syntax) before
   deploying, and deploy via Terraform with its own detail doc under
   `docs/*_BUILD_PLAN.md` recording what was confirmed and what's still open.

## A note on "already built" Plex UI reports

A Plex UI report (from `mapping/`) covering similar ground to a spreadsheet
is a **useful lead for which raw views back the business concept** — nothing
more. It is never a reason to skip building the BigQuery pipeline: the whole
point of this project is getting the data into BigQuery, and a Plex-native
report screen doesn't do that regardless of feature overlap. Treat every
"Plex Reference" column above as a hint to investigate, not a resolved
answer.
