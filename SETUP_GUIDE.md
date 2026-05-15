Plex to BigQuery - GCP Setup Guide
==================================

Audience
--------
This guide is for owners, admins, and operators who need the pipeline running in GCP.

What you need from Plex staff / super admins
--------------------------------------------
Collect these items before setup:
- Plex ODBC user name and password
- Plex CompanyCode
- Plex ODBC endpoint details (host/port)
- Confirmation that your IP ranges can access Plex ODBC
- A list of Plex views or reports that expose the fields you need
- Any required query filters or company-specific constraints

What you need in GCP
--------------------
- A GCP project
- BigQuery enabled
- Artifact Registry enabled
- Cloud Run enabled
- Cloud Scheduler enabled
- Secret Manager enabled
- A service account with access to BigQuery and Secret Manager

High-level setup flow
---------------------
1. Create BigQuery dataset and metadata table.
2. Create Secret Manager entries for Plex credentials.
3. Build and push the Docker image with the Plex ODBC driver.
4. Deploy a Cloud Run job.
5. Schedule it with Cloud Scheduler.

Terraform alternative
---------------------
If you prefer infrastructure as code, you can mirror the same steps in Terraform.
This keeps changes reviewable and repeatable but adds a small upfront setup cost.
Use Terraform for:
- Service account and IAM roles
- BigQuery dataset and metadata table
- Secret Manager secrets
- Cloud Run job and Cloud Scheduler trigger
- Required API enablement and Artifact Registry
Basic flow:
- Populate Terraform variables in terraform/variables.tf or a tfvars file.
- Run terraform init and terraform apply from terraform/.
- Create Secret Manager versions for the three Plex secrets.

Step-by-step
------------
1) Configure GCP project and region
- Decide your GCP project and region.
- Update values at the top of deploy/setup.sh.

2) Prepare Plex ODBC driver
- Get the Linux ODBC driver from Plex.
- Place extracted files into driver/ in the repo.
- Expected layout is documented in Dockerfile.

3) Run the setup script
- Make it executable and run it once:
  ./deploy/setup.sh
- The script:
  - Enables required APIs
  - Creates a service account
  - Creates BigQuery dataset and metadata table
  - Creates Secret Manager entries
  - Builds and pushes the Docker image
  - Creates a Cloud Run job
  - Creates a Cloud Scheduler trigger

4) Verify
- Confirm the Cloud Run job exists.
- Check the BigQuery dataset for the table and metadata table.
- Run a manual job execution and verify data lands.

Operational notes
-----------------
- Update env vars on the Cloud Run job if table names change.
- Rotate Plex credentials by updating Secret Manager entries.
- If Plex restricts IPs, use a VPC connector and NAT for fixed egress IPs.

Support checklist for Plex staff
--------------------------------
Share this with Plex support:
- Your company name and CompanyCode
- ODBC user to be provisioned
- ODBC access enabled for the user
- Driver package for Linux
- Any firewall/IP allowlist needs

Troubleshooting
---------------
- Driver missing: ensure driver/ contains Plex .so files before build.
- Auth issues: validate Secret Manager entries and Cloud Run env vars.
- Empty data: confirm the Plex view/report and filters.
