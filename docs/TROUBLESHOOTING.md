# Troubleshooting Cheatsheet

Last reviewed: 2026-09-25

Quick-reference commands for every common error. Copy-paste ready — substitute your project values where shown.

> **Deploying a fix:** anything Terraform manages (`terraform.tfvars`, `main.tf`, `reports/` YAML/SQL) goes out with `./scripts/deploy.sh` from the primary folder on a clean, pushed `main` — never a bare `terraform apply`. Terraform's own deploy guard refuses plan/apply anywhere else. See `CONTRIBUTING.md` § "Branches, folders and locks".

> **Project:** `voxdatalake` | **Region:** `us-central1` | **Example job:** `plex-etl-sales-orders` — one of **26** live jobs (13 pipelines × prod/test). Every recipe below substitutes cleanly for any other job name; swap `plex-etl-sales-orders` for e.g. `plex-etl-quality-nonconformance-test`.

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
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl-sales-orders" \
  --project=voxdatalake --limit=100 \
  --format="value(timestamp,textPayload)"

# Logs for a specific execution (get execution name from the run output)
gcloud logging read \
  "resource.type=cloud_run_job AND labels.\"run.googleapis.com/execution_name\"=plex-etl-XXXXX" \
  --project=voxdatalake --limit=100 \
  --format="value(timestamp,textPayload)"

# Only errors
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl-sales-orders AND severity>=ERROR" \
  --project=voxdatalake --limit=50 \
  --format="value(timestamp,textPayload)"

# Open in Cloud Console (browser)
# https://console.cloud.google.com/run/jobs/details/us-central1/plex-etl-sales-orders?project=voxdatalake
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
# terraform.tfvars exists only in the primary folder (C:/F/Parasol/plex-to-big-query), on main
# Edit terraform/terraform.tfvars: plex_host = "vox.test.odbc.plex.com"
# Back it up (command in the file's header), then deploy:
./scripts/deploy.sh
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
  [archive/APPLY_DRIVER_LICENSE.md](archive/APPLY_DRIVER_LICENSE.md)) — not a client-side
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
# terraform.tfvars exists only in the primary folder (C:/F/Parasol/plex-to-big-query), on main
# Edit terraform/terraform.tfvars: plex_odbc_user = "correct.username"
# Back it up (command in the file's header), then deploy:
./scripts/deploy.sh
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
gcloud run jobs describe plex-etl-sales-orders \
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

If fields are empty, set them in `terraform.tfvars`:

```bash
# terraform.tfvars exists only in the primary folder (C:/F/Parasol/plex-to-big-query), on main
# Edit terraform/terraform.tfvars: report_from_email / report_to_emails
# Back it up (command in the file's header), then deploy:
./scripts/deploy.sh
```

### `INFO SendGrid disabled; skipping email report`

`SENDGRID_ENABLED` is `"false"`. To enable:

```bash
# terraform.tfvars exists only in the primary folder (C:/F/Parasol/plex-to-big-query), on main
# Edit terraform/terraform.tfvars: sendgrid_enabled = "true"
# Back it up (command in the file's header), then deploy:
./scripts/deploy.sh
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

Dataset was deleted or never created. Terraform recreates it — from the primary folder on `main`:

```bash
./scripts/deploy.sh
```

The plan should show the dataset being created. The raw tables and views in it come back on each job's next run, not from Terraform.

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

SHA=$(git rev-parse --short HEAD)
docker build -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA \
             -t us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest .
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA
docker push us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:latest
```

**Not "no Terraform apply needed" — nothing at all picks this up automatically.** Cloud Run Jobs resolve their image at *update* time, not per-execution, and every job's Terraform resource has `lifecycle { ignore_changes = [image] }` so `terraform apply` won't move it either. You must explicitly redeploy:
```bash
gcloud run jobs update JOB_NAME --image=us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA --region=us-central1
```
or run `deploy/cloudbuild.yaml`'s `deploy-all` step, which does this for all 26 jobs in one build (see "Full rebuild procedure" below).

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

Terraform multiline commands fail in PowerShell. Deploy from **Git Bash** —
`./scripts/deploy.sh` is a bash script anyway. Don't reach for
`-auto-approve`: the point of `deploy.sh` is that someone reads the plan and
confirms the change count before anything is applied.

### `DEPLOY GUARD: refusing to plan/apply`

Terraform runs `scripts/tf_guard.py` on every plan, apply and destroy
(`data "external" "deploy_guard"` in `terraform/main.tf`). It refuses unless
you are in the primary folder (`C:\F\Parasol\plex-to-big-query`, not a
`ptbq-*` worktree), on `main`, with a clean working tree, and `main` equals
`origin/main`. The message lists which of those failed — fix that (switch
folder, commit, push or pull). Don't override it to apply. It also needs
`python` on `PATH` — that is what Terraform calls.

### Check what Terraform will do without applying

From the primary folder on a clean, pushed `main`:

```bash
cd terraform
terraform plan -var-file=terraform.tfvars
```

To look at drift from anywhere else (read-only), give the guard a reason:

```bash
TF_GUARD_OVERRIDE="read-only drift check from dev" terraform plan -var-file=terraform.tfvars
```

### Show current Terraform state

```bash
cd terraform
terraform state list
terraform show
```

---

## Full rebuild procedure

Use this when you've changed Python code, the email template, or Python dependencies. The change goes through a `dev*` branch and `main` like any other; then, from the primary folder on an up-to-date `main`:

```bash
# 1. Refuses unless you're on a clean main (an image deploy has no guard inside it)
./scripts/deploy_preflight.sh

# 2. Build, push, move all 26 jobs onto the new image (deploy-all step), then
#    smoke-test plex-etl-sales-orders-test. SHORT_SHA must be passed by hand.
gcloud builds submit --config deploy/cloudbuild.yaml --project=voxdatalake \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .

# 3. Run a prod job manually to verify (Cloud Build never runs prod)
gcloud run jobs execute plex-etl-sales-orders \
  --region=us-central1 --project=voxdatalake --wait

# 4. Check logs
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=plex-etl-sales-orders" \
  --project=voxdatalake --limit=50 \
  --format="value(timestamp,textPayload)"
```

Pushing an image alone moves nothing — every job's `lifecycle { ignore_changes = [image] }` means neither a push nor `terraform apply` changes the image a job runs. If Cloud Build isn't available, the manual equivalent after `docker build`/`docker push` of an `:$SHA` tag is `gcloud run jobs update` on **every** job in `_ALL_JOBS` in `deploy/cloudbuild.yaml` (26 names, `plex-etl-<pipeline>` and `plex-etl-<pipeline>-test`):

```bash
for job in $(grep '_ALL_JOBS:' deploy/cloudbuild.yaml | cut -d'"' -f2); do
  gcloud run jobs update "$job" --image=us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl:$SHA --region=us-central1
done
```

Changed `terraform.tfvars` as well? That is a separate `./scripts/deploy.sh`.

---

## Config changes that DON'T need a rebuild

These only need a `terraform.tfvars` edit (in the primary folder, the only place that file exists — back it up afterwards, see its header) and `./scripts/deploy.sh`:

| What you're changing | Variable in tfvars |
|---|---|
| Plex host (test vs production) | `plex_host` |
| Email on/off | `sendgrid_enabled` |
| Sender email | `report_from_email` |
| Recipients | `report_to_emails` |
| Company name (subject's no-category fallback) | `company_name` |
| How far back to backfill | `backfill_minutes` |

**`plex_view`/`plex_filter`/`plex_date_col`/`bq_table` are legacy single-view-mode fallbacks — no live job uses them.** Every real job sets `REPORT_CONFIG_GCS_PATH`, which bypasses these entirely. To change what a report queries or filters, edit that report's YAML pair (`reports/<pipeline>.yaml` and `reports/test/<pipeline>.yaml`, `extractions[]`) on a `dev*` branch, merge to `main`, and `./scripts/deploy.sh` — Terraform uploads the YAML to GCS and the job picks it up on its next run. See `docs/OPERATIONS.md` § "Edit an Existing Report".

Secrets (token, API key, password) can be rotated with a single `gcloud secrets versions add` command — no Terraform apply, no rebuild.

---

## Nuke and redeploy to a new project

Full procedure in [docs/TEARDOWN.md](TEARDOWN.md). Summary — this creates the **entire stack** (26 jobs, 52 schedulers, about 200 resources), not one job. Every `terraform` command below passes the deploy guard, so run them from the primary folder on a clean, pushed `main`; the `main.tf` edits TEARDOWN asks for are commits to `main` first, not local edits.

```bash
# 1. Destroy all GCP resources (from terraform/, after TEARDOWN.md steps 1-4)
terraform destroy -var-file=terraform.tfvars

# 2. Update terraform.tfvars with the new project ID and a real (not :latest) image tag
#    gcp_project = "new-project-id"
#    image_url   = "us-central1-docker.pkg.dev/new-project-id/plex-pipeline/etl:$SHA"
#    (plus the backend bucket in main.tf, committed — see TEARDOWN.md)

# 3. Create the infrastructure. Cloud Run jobs fail to create until the image exists — expected
cd terraform && terraform init && cd ..
./scripts/deploy.sh

# 4. Push the image to the new project's registry — tag with a commit SHA, never ":latest"
gcloud auth configure-docker us-central1-docker.pkg.dev --project=new-project-id
SHA=$(git rev-parse --short HEAD)
docker build -t us-central1-docker.pkg.dev/new-project-id/plex-pipeline/etl:$SHA .
docker push us-central1-docker.pkg.dev/new-project-id/plex-pipeline/etl:$SHA
# Deploy again so the jobs get created on the now-real image (this only works
# because they don't exist yet — on every later rebuild, ignore_changes means
# apply won't touch the image; see "Full rebuild procedure" above)
./scripts/deploy.sh

# 5. Re-populate ALL FIVE secrets in the new project
echo -n 'TOKEN'    | gcloud secrets versions add plex-access-token  --data-file=- --project=new-project-id
echo -n 'SG.key'   | gcloud secrets versions add sendgrid-api-key   --data-file=- --project=new-project-id
echo -n 'USER'     | gcloud secrets versions add plex-odbc-user     --data-file=- --project=new-project-id
echo -n 'PASSWORD' | gcloud secrets versions add plex-odbc-password --data-file=- --project=new-project-id
echo -n 'CODE'     | gcloud secrets versions add plex-company-code  --data-file=- --project=new-project-id

# 6. Nothing to upload by hand: every reports/ YAML and SQL file is a Terraform-managed
#    GCS object, created in step 3. BUT every YAML's sql_file is a hardcoded
#    gs://voxdatalake-report-configs/... URI — a bucket with a different name
#    needs those URIs changed (and committed) first.

# 7. Run each job to verify — at minimum, every *-test job:
for job in $(grep '_ALL_JOBS:' deploy/cloudbuild.yaml | cut -d'"' -f2 | tr ' ' '\n' | grep -- '-test$'); do
  gcloud run jobs execute "$job" --region=us-central1 --project=new-project-id --wait
done
```
