# Troubleshooting Cheatsheet

Quick-reference commands for every common error. Copy-paste ready — substitute your project values where shown.

> **Project:** `voxdatalake` | **Region:** `us-central1` | **Job:** `plex-etl`

---

## Table of contents

- [View logs](#view-logs)
- [Secret / API key errors](#secret--api-key-errors)
- [Plex ODBC errors](#plex-odbc-errors)
- [SendGrid / email errors](#sendgrid--email-errors)
- [BigQuery errors](#bigquery-errors)
- [Docker build & push](#docker-build--push)
- [Terraform errors](#terraform-errors)
- [Full rebuild procedure](#full-rebuild-procedure)
- [Nuke and redeploy to a new project](#nuke-and-redeploy-to-a-new-project)

---

## View logs

```bash
# Logs for the most recent execution (last 100 lines)
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl" \
  --project=voxdatalake --limit=100 \
  --format="value(timestamp,textPayload)"

# Logs for a specific execution (get execution name from the run output)
gcloud logging read \
  "resource.type=cloud_run_job AND labels.\"run.googleapis.com/execution_name\"=plex-etl-XXXXX" \
  --project=voxdatalake --limit=100 \
  --format="value(timestamp,textPayload)"

# Only errors
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl AND severity>=ERROR" \
  --project=voxdatalake --limit=50 \
  --format="value(timestamp,textPayload)"

# Open in Cloud Console (browser)
# https://console.cloud.google.com/run/jobs/details/us-central1/plex-etl?project=voxdatalake
```

---

## Secret / API key errors

### `google.api_core.exceptions.NotFound: Secret … has no versions`

The secret container exists but no value has been stored.

```bash
# Store the Plex IAM access token
echo -n 'YOUR_TOKEN_HERE' | \
  gcloud secrets versions add plex-access-token \
  --data-file=- --project=voxdatalake

# Store the SendGrid API key (starts with SG.)
echo -n 'SG.your-key-here' | \
  gcloud secrets versions add sendgrid-api-key \
  --data-file=- --project=voxdatalake
```

### `google.api_core.exceptions.PermissionDenied: … secretmanager.versions.access`

The Cloud Run service account doesn't have permission to read secrets.

```bash
gcloud projects add-iam-policy-binding voxdatalake \
  --member="serviceAccount:plex-etl-sa@voxdatalake.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Expired Plex IAM access token (ODBC auth fails after working fine)

Plex IAM tokens expire. Generate a new one in the Plex portal, then overwrite:

```bash
echo -n 'NEW_TOKEN_HERE' | \
  gcloud secrets versions add plex-access-token \
  --data-file=- --project=voxdatalake
```

No Terraform apply or Docker rebuild needed — the job reads the secret at runtime.

### Check what value is stored in a secret

```bash
gcloud secrets versions access latest \
  --secret=plex-access-token --project=voxdatalake

gcloud secrets versions access latest \
  --secret=sendgrid-api-key --project=voxdatalake
```

### List all secret versions and their state

```bash
gcloud secrets versions list plex-access-token --project=voxdatalake
gcloud secrets versions list sendgrid-api-key --project=voxdatalake
```

---

## Plex ODBC errors

### `HY000 [10300] The requested service was not found`

The `ServerDataSource` doesn't exist on the host you're pointing at. This happens when using `vox.odbc.plex.com` (production) with a `ServerDataSource` name that's only registered on the test host.

```bash
# Switch to test host (works with ReportDataSource)
cd terraform
# Edit terraform.tfvars: plex_host = "vox.test.odbc.plex.com"
terraform apply -var-file=terraform.tfvars
```

For production: contact Plex support to confirm the correct `ServerDataSource` name for `vox.odbc.plex.com`. (As of 2026-07-20, `ReportDataSource` is confirmed working on both hosts — this error is more likely to resurface if the `ServerDataSource` name is ever changed on one side only.)

### `08S01 [2404] Session refused by service, connection closed`

```
[DataDirect][ODBC OpenAccess SDK driver][OpenAccess SDK Client]Session
refused by service, connection closed (2404) (SQLDriverConnect)
```

The TCP connection and driver handshake succeed, but Plex's OpenAccess SDK
service actively refuses to open a session. This is **not** a network,
driver-config, license, or token problem — confirmed on 2026-07-19/20 by
ruling out all four:

- Reproduced identically from two independent networks (Google Cloud Run
  and a separate office/home network) — not a firewall/IP-allowlist issue.
- Reproduced identically with a brand-new IAM token — not a token
  validity/expiry issue.
- Persisted after properly licensing the DataDirect driver (see
  [APPLY_DRIVER_LICENSE.md](APPLY_DRIVER_LICENSE.md)) — not a client-side
  license issue.
- The identical account/token connects successfully to the test host
  throughout — rules out the account being globally disabled.

This is an **account/session-level authorization restriction specific to
that Plex environment** (e.g. ODBC/OpenAccess SDK reporting access not
enabled for this account on production, even though normal Plex application
login and reporting work fine — those are separate subsystems with
separate entitlements). Contact Plex Support and ask them to confirm ODBC
report-session access is enabled for the account on the affected
environment. Rule out the four causes above first if this recurs somewhere
new, since a fresh occurrence could have a different root cause.

### `HY000 [3059] Token is expired / invalid`

The IAM access token stored in Secret Manager is no longer valid.

```bash
# Overwrite with a fresh token (no rebuild needed)
echo -n 'NEW_TOKEN_HERE' | \
  gcloud secrets versions add plex-access-token \
  --data-file=- --project=voxdatalake
```

### `HY000 Login failed`

Wrong ODBC username. The format must be `username.company` (e.g. `edominguez.parasol`).

```bash
# Update the env var via terraform (no rebuild needed)
# Edit terraform.tfvars: plex_odbc_user = "correct.username"
cd terraform && terraform apply -var-file=terraform.tfvars
```

### Driver prints license warning but job still runs

```
[DataDirect][ODBC OpenAccess SDK driver] You are not licensed...
```

This is a **warning**, not an error — the job continues. It means the Plex ODBC driver detects it's being called from an application that isn't on the licensed allow-list. As long as your Plex subscription covers ODBC access, this warning is cosmetic. If jobs start failing with a hard license error, contact Plex support.

---

## SendGrid / email errors

### `HTTP Error 401: Unauthorized`

The API key stored in Secret Manager is wrong or has been revoked.

1. Go to `app.sendgrid.com` → Settings → API Keys
2. Create a new key (Restricted → Mail Send)
3. Re-store it:

```bash
echo -n 'SG.new-key-here' | \
  gcloud secrets versions add sendgrid-api-key \
  --data-file=- --project=voxdatalake
```

### `WARNING SendGrid config incomplete; skipping email report`

One of three required fields is missing from the Cloud Run job: API key, `REPORT_FROM_EMAIL`, or `REPORT_TO_EMAILS`.

```bash
# Check what env vars are currently deployed
gcloud run jobs describe plex-etl \
  --region=us-central1 --project=voxdatalake --format=json \
  | python3 -c "
import json,sys
j=json.load(sys.stdin)
envs=j['spec']['template']['spec']['template']['spec']['containers'][0].get('env',[])
for e in envs:
  name=e.get('name','')
  if any(k in name for k in ['SENDGRID','REPORT','COMPANY']):
    print(f\"{name}={e.get('value','')!r}\")
"
```

If fields are empty: edit `terraform.tfvars`, then:

```bash
cd terraform && terraform apply -var-file=terraform.tfvars
```

### `INFO SendGrid disabled; skipping email report`

`SENDGRID_ENABLED` is `"false"`. To enable:

```bash
# Edit terraform.tfvars: sendgrid_enabled = "true"
cd terraform && terraform apply -var-file=terraform.tfvars
```

### Email sends (status 202) but lands in spam

The sender email isn't domain-authenticated. In SendGrid → Settings → Sender Authentication → set up Domain Authentication for `parasolgroupinc.com`.

---

## BigQuery errors

### `403 Access Denied: Table … user does not have bigquery.tables.create`

```bash
gcloud projects add-iam-policy-binding voxdatalake \
  --member="serviceAccount:plex-etl-sa@voxdatalake.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"
```

### `404 Not found: Dataset voxdatalake:PlexTest`

Dataset was deleted or never created. Re-apply Terraform:

```bash
cd terraform && terraform apply -var-file=terraform.tfvars
```

### Check what's in BigQuery

```bash
# List tables
bq ls --project_id=voxdatalake PlexTest

# Row count
bq query --project_id=voxdatalake --nouse_legacy_sql \
  "SELECT COUNT(*) FROM \`voxdatalake.PlexTest.raw_Part_v_Part\`"

# Last sync timestamp
bq query --project_id=voxdatalake --nouse_legacy_sql \
  "SELECT * FROM \`voxdatalake.PlexTest.sync_metadata\` ORDER BY synced_at DESC LIMIT 5"

# Preview data
bq query --project_id=voxdatalake --nouse_legacy_sql \
  "SELECT * FROM \`voxdatalake.PlexTest.raw_Part_v_Part\` LIMIT 10"
```

---

## Docker build & push

### Standard rebuild (after any code or template change)

```bash
# From project root
gcloud auth configure-docker us-central1-docker.pkg.dev --project=voxdatalake

docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest .
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest
```

Cloud Run always pulls `:latest` on the next execution — no Terraform apply needed after a push.

### `denied: Unauthenticated request`

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev --project=voxdatalake
gcloud auth login
```

### `COPY driver/ /usr/oaodbc81/` fails — directory not found

The `driver/` folder is gitignored and must be obtained from Plex. It is not in the repo.

```
driver/
  lib64/
    ivoa27.so       ← main ODBC driver
    ddtrc27.so      ← trace library
  rscshell          ← 32-bit utility
```

Contact Plex support or log in to the Plex portal to download the Linux ODBC driver package, then extract it into `driver/`.

### Updating the ODBC driver

When Plex releases a new driver version:
1. Download the new Linux driver from the Plex portal
2. Extract into `driver/` (overwrite existing files)
3. Rebuild and push the image (see above)
4. Run the job to verify

The driver version number is in the `.so` filename — `ivoa27.so` means version 2.7. If the filename changes (e.g. `ivoa28.so`), also update:
- `Dockerfile` line: `ENV LD_LIBRARY_PATH=/usr/oaodbc81/lib64`
- `config/odbcinst.ini` — the `Driver=` path
- `main.py` line: `"DRIVER={/usr/oaodbc81/lib64/ivoa27.so};"`

### Where the driver license lives

The DataDirect ODBC license is **not a separate file you manage**. It is tied to your Plex subscription and enforced server-side by Plex. The warning `You are not licensed to use this Progress Software product` is printed by the driver DLL itself and is cosmetic as long as your Plex account has ODBC access enabled. If Plex ever disables ODBC access on your account, the connection will fail with a hard error — not just a warning.

---

## Terraform errors

### `Error 409: … already exists`

A GCP resource was created outside of Terraform (manually, or from a previous deploy) and isn't in Terraform state. Import it:

```bash
cd terraform

# Examples — substitute the correct resource address from the error message
terraform import google_secret_manager_secret.sendgrid_api_key \
  projects/voxdatalake/secrets/sendgrid-api-key

terraform import google_bigquery_dataset.plex \
  projects/voxdatalake/datasets/PlexTest

terraform import google_artifact_registry_repository.etl \
  projects/voxdatalake/locations/us-central1/repositories/plex-pipeline
```

### `Error 403: … caller does not have permission`

Your gcloud account doesn't have Owner or the required role on this project.

```bash
# Check who you're logged in as
gcloud auth list

# Check your roles on the project
gcloud projects get-iam-policy voxdatalake \
  --flatten="bindings[].members" \
  --format="table(bindings.role,bindings.members)" \
  --filter="bindings.members:$(gcloud config get-value account)"
```

### `Too many command line arguments` (Windows PowerShell)

Terraform multiline commands fail in PowerShell. Use Git Bash, or pass vars as a single line:

```bash
terraform apply -var-file=terraform.tfvars -auto-approve
```

### Check what Terraform will do without applying

```bash
cd terraform
terraform plan -var-file=terraform.tfvars
```

### Show current Terraform state

```bash
cd terraform
terraform state list
terraform show
```

---

## Full rebuild procedure

Use this when you've changed Python code, the email template, or Python dependencies.

```bash
# 1. Make your code changes
# 2. Rebuild and push the image
docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest .
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest

# 3. (Optional) Apply any terraform.tfvars changes at the same time
cd terraform && terraform apply -var-file=terraform.tfvars

# 4. Run manually to verify
gcloud run jobs execute plex-etl \
  --region=us-central1 --project=voxdatalake --wait

# 5. Check logs
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl" \
  --project=voxdatalake --limit=50 \
  --format="value(timestamp,textPayload)"
```

---

## Config changes that DON'T need a rebuild

These only need `terraform apply` (takes ~30 seconds):

| What you're changing | Variable in tfvars |
|---|---|
| Plex host (test vs production) | `plex_host` |
| Which Plex view to query | `plex_view` |
| SQL filter | `plex_filter` |
| Timestamp column for incremental sync | `plex_date_col` |
| Target BigQuery table name | `bq_table` |
| Email on/off | `sendgrid_enabled` |
| Sender email | `report_from_email` |
| Recipients | `report_to_emails` |
| Company name in email subject | `company_name` |
| How far back to backfill | `backfill_minutes` |

Secrets (token, API key, password) can be rotated with a single `gcloud secrets versions add` command — no Terraform apply, no rebuild.

---

## Nuke and redeploy to a new project

Full procedure in [docs/TEARDOWN.md](TEARDOWN.md). Summary:

```bash
# 1. Destroy all GCP resources (run from terraform/)
#    First: manually set delete_contents_on_destroy = true in main.tf
#    and deletion_protection = false on the sync_metadata table
terraform destroy -var-file=terraform.tfvars

# 2. Update terraform.tfvars with the new project ID
#    gcp_project = "new-project-id"
#    image_url   = "us-central1-docker.pkg.dev/new-project-id/plex-pipeline/etl:latest"

# 3. Re-deploy
terraform apply -var-file=terraform.tfvars

# 4. Push the image to the new project's registry
gcloud auth configure-docker us-central1-docker.pkg.dev --project=new-project-id
docker build -t us-central1-docker.pkg.dev/new-project-id/plex-pipeline/etl:latest .
docker push us-central1-docker.pkg.dev/new-project-id/plex-pipeline/etl:latest

# 5. Re-populate secrets in the new project
echo -n 'TOKEN' | gcloud secrets versions add plex-access-token \
  --data-file=- --project=new-project-id
echo -n 'SG.key' | gcloud secrets versions add sendgrid-api-key \
  --data-file=- --project=new-project-id

# 6. Run to verify
gcloud run jobs execute plex-etl \
  --region=us-central1 --project=new-project-id --wait
```
