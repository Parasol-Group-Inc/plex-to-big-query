# Plex Reports & Data Sources Catalog

Reference doc for the `mapping/` folder — a snapshot of what the Plex portal
(vox.test.on.plex.com) exposes at the **UI report** and **stored-procedure**
layers, as opposed to the raw ODBC **views** documented in [`catalog/`](../catalog/plex_catalog_index.md).

Source data lives in `mapping/*.md` / `.csv` / `.json`. This doc is a guide to
that folder, not a duplicate of it — the full row-level detail (1,153 reports,
14,350 data sources) is impractical to inline here.

## The three layers — don't conflate them

| Layer | Where documented | How it's queried | Example |
|---|---|---|---|
| **ODBC views** | [`catalog/plex_*_views_catalog.md`](../catalog/plex_catalog_index.md) | `SELECT * FROM {Database}_v_{ViewName}` — what `reports/*.yaml` extractions use today | `Sales_v_PO` |
| **UI reports** | [`mapping/available-reports.md`](../mapping/available-reports.md), [`mapping/enabled-reports.md`](../mapping/enabled-reports.md) | Not queryable at all — these are report *screens* in the Plex web UI, identified by `ReportKey` | "Open Purchase Orders" |
| **Data sources** | [`mapping/data-sources.md`](../mapping/data-sources.md), [`mapping/data-sources-accessible.md`](../mapping/data-sources-accessible.md) | Mostly **stored procedures** taking input parameters, called via `CustomerDataSourceManager` / API — not a plain `SELECT` | `Open_PO_Get` (10 inputs) |

Confirmed by direct comparison: none of the 152 enabled UI report titles match
an ODBC view name or a data-source name verbatim. When scoping a new
BigQuery report, the ODBC views catalog is almost always the right place to
start — the UI reports and data-sources catalogs are useful for figuring out
**what a business report is called and roughly what data it needs**, not for
finding a queryable object directly.

> ⚠ A data source with `GlobalAllow: true` / `SelfServiceable: 1` (e.g.
> `Open_PO_Get`) is *reachable*, but it's still a parameterized stored
> procedure. The current `main.py` extraction pattern only issues
> `SELECT * FROM {view}` — it has no stored-procedure-call support. Don't
> treat an accessible data source as a drop-in replacement for a view.

## `available-reports` — full Plex UI report catalog

1,153 reports across 20 Module Groups, pulled via the unpaginated
`SearchAvailableReports` API. See the table of contents in
[`mapping/available-reports.md`](../mapping/available-reports.md) for the
full per-module breakdown (Accounting 166, Costing 84, Sales and CRM 121,
Production Tracking 129, Quality 111, Shipping 85, etc.).

## `enabled-reports` — what's actually turned on for Vox

152 of the 1,153 reports (13 Module Groups) are enabled/selected for this
tenant, filtered via the `Selected` flag. Full list in
[`mapping/enabled-reports.md`](../mapping/enabled-reports.md). Notable
because an enabled report is a report a Vox user can already run and see
data for today — useful for sanity-checking whether a report we're asked to
build in BigQuery already exists as a live Plex screen (and what fields it
shows) before reverse-engineering it from raw views.

## `data-sources` / `data-sources-accessible` — stored procedures catalog

14,350 objects from `Platform > CustomerDataSourceManager`, 28 databases,
mostly `Stored Procedure` type (some `API Plugin`). Full breakdown in
[`mapping/data-sources.md`](../mapping/data-sources.md). The
`data-sources-accessible` shortlist (1,327 rows) filters to
`GlobalAllow: true` and/or `SelfServiceable: 1` — see
[`mapping/data-sources-accessible.md`](../mapping/data-sources-accessible.md).
Treat the shortlist as a starting point to validate, not a guaranteed-working
list — the doc's own caveat is that tenant-level enablement can still be
required even when these flags are set.

## When to use this vs. `catalog/`

- Need to know **what raw view backs a field** → [`catalog/`](../catalog/plex_catalog_index.md)
- Need to know **what a business report is called / whether it's enabled** → `mapping/available-reports.md` / `mapping/enabled-reports.md`
- Need to know **whether a stored-proc data source exists for something with no raw view** → `mapping/data-sources.md` (but expect to hit the parameterized-call limitation above)

See [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](NETSUITE_REPORT_BUILD_PLAN.md) for
a worked example of using all three catalogs together to scope new reports.
