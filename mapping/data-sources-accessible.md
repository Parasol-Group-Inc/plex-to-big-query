# Vox Nutrition — Accessible ODBC Data Sources (Shortlist)

Filtered from [data-sources.json](data-sources.json) (14,350 total) down to rows flagged as `GlobalAllow: true` and/or `SelfServiceable: 1` — the ones plausibly reachable over ODBC without a separate vendor/Plex-support request to enable them.

**Caveat:** these flags reflect what the platform generally permits; your tenant may still need each one explicitly turned on in Plex before ODBC can actually query it. Treat this as a starting shortlist to validate against, not a guaranteed-working list.

**Total shortlisted:** 1327 (of 14,350)  
- Global Allow + Self Serviceable: 1244  
- Global Allow only: 31  
- Self Serviceable only: 52  

## By Database

| Database | Count |
|---|---|
| Part | 656 |
| Sales | 193 |
| Common | 132 |
| Accounting | 72 |
| Quality | 71 |
| Purchasing | 63 |
| Personnel | 41 |
| Communication | 37 |
| Maintenance | 26 |
| Plexus_Control | 11 |
| Material | 8 |
| Cloud | 6 |
| Label | 5 |
| null | 3 |
| EDI | 1 |
| External | 1 |
| Web_Services | 1 |

---

Full row-level detail is in [data-sources-accessible.json](data-sources-accessible.json) and [data-sources-accessible.csv](data-sources-accessible.csv).
