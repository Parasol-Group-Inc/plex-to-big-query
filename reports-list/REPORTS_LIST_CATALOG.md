# Reports List Catalog

Hub for a different, bigger master spreadsheet: **"Reports List"**, a
company-wide inventory of every report/tracker in use across departments —
regardless of source system (NetSuite, DataNinja, Excel, Monday.com,
network shares, and Google Sheets). One tab per department; each row is
one report with its Source, Function, Users, Link, and Priority.

This is **not** the same thing as [`spreadsheets/`](../spreadsheets/), which
tracks individual Google Sheets this project is actively mapping to Plex.
Reports List is the wider net that surfaces *candidates* for that folder —
most rows here are sourced from systems this pipeline has no access to at
all (NetSuite, DataNinja, Monday.com, local Excel/network shares) and are
explicitly **out of scope** for this Plex→BigQuery ETL project. Only the
Google-Sheet-sourced rows are real candidates, and only some of those.

## Tabs

| Tab | File | What's in it |
|---|---|---|
| [Production](production.md) | `Reports List - Production.csv` | MFG/Bottling Job Schedules, Daily Reports — heaviest overlap with `spreadsheets/` |
| [Quality](quality.md) | `Reports List - Quality.csv` | QA/compliance trackers — includes 9 reports explicitly marked **"New W Plex"**, i.e. already-identified-but-unbuilt Plex-based reports |
| [Supply Chain](supply-chain.md) | `Reports List - Supply Chain.csv` | Purchasing/inventory reports — includes 2 rows that are the exact NetSuite reports this project already built parity for |
| [Sales](sales.md) | `Reports List - Sales.csv` | Almost entirely NetSuite saved searches — out of scope, catalogued for completeness |
| [Warehouse](warehouse.md) | `Reports List - Warehouse.csv` | One row (Cycle Count), no usable link yet |
| [NS Reference](ns-reference.md) | `Reports List - NS Reference.csv` | Flat list of NetSuite report names — cross-referenced against already-built NetSuite parity reports and `mapping/netsuite-report-mapping.md` |

## How to read a row's status

Every row across every tab gets one of:

- ❌ **Out of scope** — sourced from NetSuite, DataNinja, Monday.com, Excel,
  or a network share. This pipeline reads from Plex ODBC only; these are
  different systems entirely, not a gap to close here.
- ✅ **Already built** — this project already shipped a BigQuery report
  covering this, cross-referenced to `docs/NETSUITE_REPORT_BUILD_PLAN.md`,
  `docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md`, or `spreadsheets/SPREADSHEET_CATALOG.md`.
- 🎯 **Candidate — New W Plex** — the report's own Source/Link field
  literally says "New W Plex," meaning someone already flagged this as a
  wanted-but-unbuilt Plex-based report. Highest-value target list.
- 🔍 **Candidate — Google Sheet** — sourced from a Google Sheet, not yet
  analyzed. Needs the same treatment as `spreadsheets/`: real content
  before any column mapping.
- 💡 **Idea, no source yet** — listed as "Nice to have" with no real
  system backing it. Not a mapping target until it exists somewhere.

## Cross-references worth knowing

- `Reports List - NS Reference.csv` overlaps heavily with
  `mapping/netsuite-report-mapping.md` (same underlying NetSuite report
  catalog this project's original NetSuite parity build plan was scoped
  from) — see [ns-reference.md](ns-reference.md).
- "Quality | Bottling Production Search" and "Quality | Encapsulation
  Production Search" (appearing in both the Quality tab and NS Reference
  tab, despite the "NS" name) actually link to the **Bottling Job
  Schedule** and **MFG Job Schedule** Google Sheets respectively — not
  NetSuite at all. Naming is misleading; the link is the ground truth.
- "Approaching MSL" (Supply Chain tab) is described as feeding "current
  available inventory" into MFG Job Schedule — i.e. it may be the current
  *manual* source of the exact number `part_on_hand_inventory_report`
  (built from `Part_v_Container`) now automates. Worth comparing once its
  content is available — see [supply-chain.md](supply-chain.md).
