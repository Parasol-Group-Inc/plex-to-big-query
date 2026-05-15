Plex to BigQuery - Technical Dive
=================================

Purpose
-------
This document explains how the pipeline is built, how data flows, and where to extend it.

Core files
----------
- main.py: ETL logic and metadata handling
- Dockerfile: runtime image and driver setup
- deploy/setup.sh: one-time GCP setup
- deploy/cloudbuild.yaml: CI build and deploy
- config/odbc.ini + config/odbcinst.ini: DSN and driver registration

Data flow
---------
1. Cloud Run job starts and reads env vars.
2. Secrets are pulled from Secret Manager.
3. ODBC connects to Plex via DSN.
4. Data is queried using Modified_Date for incremental loads.
5. Data is appended into BigQuery.
6. Sync metadata is written to the metadata table.

Incremental logic
-----------------
- The job uses a backfill window to avoid missed boundary updates.
- It records max Modified_Date observed in each run.
- The next run uses that max timestamp as the baseline.
- Backfill window is configurable with BACKFILL_MINUTES.

Metadata table
--------------
Table name is set by METADATA_TABLE (default: sync_metadata).
Schema:
- table_name: STRING
- last_sync_at: TIMESTAMP
- max_modified_at: TIMESTAMP
- rows_written: INTEGER
- synced_at: TIMESTAMP

BigQuery load behavior
----------------------
- Uses WRITE_APPEND on each run.
- If you need upserts, add a staging table and MERGE on a business key.
- Consider moving to an explicit schema to prevent inference drift.

Configuration knobs
-------------------
Environment variables:
- GCP_PROJECT
- BQ_DATASET
- BQ_TABLE
- PLEX_DSN (default: PlexProduction)
- METADATA_TABLE (default: sync_metadata)
- BACKFILL_MINUTES (default: 5)
- SECRET_ODBC_USER
- SECRET_ODBC_PASSWORD
- SECRET_COMPANY_CODE
- SENDGRID_ENABLED (default: false)
- SENDGRID_API_KEY
- REPORT_FROM_EMAIL
- REPORT_TO_EMAILS (comma-separated)
- REPORT_SUBJECT (optional)
- REPORT_TEMPLATE (optional; default: report.html)

ODBC notes
----------
- The Plex ODBC driver requires 32-bit compatibility libs in the container.
- config/odbc.ini and config/odbcinst.ini must match the driver paths.
- CompanyCode is injected at runtime via CustomProperties.

Extending the query
-------------------
- Replace the SQL in main.py with your Plex view/report.
- Ensure Modified_Date is included and indexed in Plex.
- Add additional fields to match downstream reporting needs.

Deployment model
----------------
- A Cloud Run job is built from the Dockerfile.
- Cloud Scheduler triggers it on a cron schedule.
- deploy/cloudbuild.yaml can auto-deploy on pushes to main.

Terraform alternative
---------------------
Terraform can provision the same resources as deploy/setup.sh with a small
module surface. This keeps infra changes versioned and auditable. Recommended
resource set:
- Service account with BigQuery and Secret Manager access
- BigQuery dataset and metadata table
- Secret Manager secrets for Plex credentials
- Cloud Run job definition with env vars
- Cloud Scheduler job to trigger Cloud Run
- Required API enablement and Artifact Registry
- Scheduler service agent token creator binding

Terraform layout
----------------
- terraform/main.tf: core resources
- terraform/variables.tf: input variables

Operational reliability
-----------------------
- Enable retries in Cloud Run job for transient errors.
- Add alerting on Cloud Run job failures and BigQuery load errors.
- Consider a staging table and MERGE to handle updates cleanly.

Email report template
---------------------
The HTML template lives in templates/report.html and is rendered with simple
placeholders. Keep it free of external assets for reliable delivery.
