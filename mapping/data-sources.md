# Vox Nutrition — ODBC Data Sources Catalog

Objects exposed via Plex ODBC (Platform > Data Sources / CustomerDataSourceManager), fetched via the SearchAvailableReports-equivalent endpoint `/Platform/CustomerDataSourceManager/Search?limit=false`.

These are distinct from the [Available Reports catalog](available-reports.md) / [Enabled Reports catalog](enabled-reports.md) — Data Sources are raw stored procedures (e.g. `Add_Unscheduled_Workcenters_Picker_Get`), not UI report screens. Confirms none of the enabled report titles correspond to ODBC-queryable objects here.

**Total data sources:** 14350  
**Distinct databases:** 28  
**Global Allow = true:** 1275  
**Self Serviceable (non-zero):** 1296  
**With a Module/ModuleGroup assigned:** 7150

## By Database

| Database | Count |
|---|---|
| Part | 4029 |
| Sales | 1831 |
| Quality | 1386 |
| Common | 1308 |
| Accounting | 1148 |
| Plexus_Control | 892 |
| Personnel | 850 |
| Purchasing | 513 |
| Communication | 387 |
| EDI | 384 |
| Label | 382 |
| Cloud | 182 |
| Plexus_Rendering | 172 |
| Maintenance | 166 |
| ERLog | 149 |
| External | 136 |
| Web_Services | 119 |
| Material | 86 |
| Document | 78 |
| Steel | 77 |
| Plex_Global | 34 |
| Report_Services | 20 |
| Plexus_System | 7 |
| Community | 6 |
| null | 3 |
| Transteq | 3 |
| Development | 1 |
| master | 1 |

---

Full row-level detail (all 14,350 entries) is in [data-sources.json](data-sources.json) and [data-sources.csv](data-sources.csv) — a flat listing here would be impractical to browse.
