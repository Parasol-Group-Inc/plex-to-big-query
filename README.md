Plex to BigQuery
================

What it does
------------
This project moves operational data from Plex into BigQuery on a schedule.
It keeps BigQuery up to date so reports and dashboards can run in one place.

Who this is for
---------------
- Business owners who want reliable data in BigQuery.
- Analysts who need Plex data without pulling reports by hand.
- Developers who operate the pipeline.

How it works (plain English)
----------------------------
1. A scheduled job runs in Google Cloud.
2. The job connects to Plex using the ODBC driver.
3. New and updated records are pulled.
4. The data is written into BigQuery.

Where to go next
---------------
- Setup and admin checklist: SETUP_GUIDE.md
- Technical details for developers: TECHNICAL_DIVE.md
- Terraform alternative setup notes: TECHNICAL_DIVE.md
