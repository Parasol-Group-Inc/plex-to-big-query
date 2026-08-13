# Infrastructure Teardown Guide

> Use this when you need to completely remove all GCP resources — for example, to redeploy to a different project, or to decommission the pipeline.
>
> **This is destructive and irreversible.** BigQuery data, Secret Manager versions, and Docker images will be permanently deleted.

---

## What gets deleted

As of 2026-08-13 there are **16 Cloud Run jobs** (8 report families × prod/test), **32 Cloud Scheduler jobs** (one daily + one 6 AM Mountain retry trigger per Cloud Run job), **5** Secret Manager containers, and **2** BigQuery datasets (`PlexProd` + `PlexTest`) — not the single-job/single-dataset/4-secret setup this table used to describe. `terraform destroy` removes all of it in one pass regardless — the table below is just for understanding what's actually in scope, not something you enumerate by hand.

| Resource | Managed by | Deleted how |
|---|---|---|
| All 16 Cloud Run jobs (`plex-etl`, `plex-etl-work-orders(-test)`, etc.) | Terraform | `terraform destroy` |
| All 32 Cloud Scheduler jobs (16 daily + 16 retry) | Terraform | `terraform destroy` |
| BigQuery datasets `PlexProd` + `PlexTest` + all tables/views in both | Terraform | `terraform destroy` (after unlocking — see Step 2) |
| `report_configs` GCS bucket (`voxdatalake-report-configs` — every `reports/*.yaml`/`*.sql`) | Terraform | `terraform destroy` |
| Artifact Registry repo (`plex-pipeline`) | Terraform | `terraform destroy` (after clearing images) |
| Secret Manager containers (5 secrets: access token, SendGrid key, ODBC user/password, company code) | Terraform | `terraform destroy` |
| Secret versions (the actual token/key values) | Manual | Deleted with the container |
| Service account (`plex-etl-sa`) | Terraform | `terraform destroy` |
| IAM role bindings | Terraform | `terraform destroy` |
| GCP APIs enabled | Terraform | Left enabled (harmless, free) |
| Docker image layers | Manual | Must clear before destroy |
| Every `raw_*` table (dozens — one per `bq_table:` entry across all 8 `reports/*.yaml`) | ETL job (not Terraform) | Created dynamically at runtime, not tracked by Terraform. `delete_contents_on_destroy = true` (Step 2) handles this for you — no need to delete them one by one. |
| Terraform state bucket (`voxdatalake-terraform-state`) | Not managed by Terraform | `terraform destroy` never touches this — it lives outside the config on purpose so destroy can't delete its own state. Also holds the `terraform.tfvars.backup` object (see that file's own header) — back that up elsewhere first if you're deleting this bucket for real. Delete manually (`gcloud storage rm -r gs://voxdatalake-terraform-state`) only if decommissioning the project entirely. |

---

## Step 1 — Pause the scheduler

Stop any new runs from starting while you tear things down:

```bash
gcloud scheduler jobs pause plex-daily-sync \
  --location=us-central1 --project=voxdatalake
```

---

## Step 2 — Unlock Terraform-protected resources

**Only one change needed as of 2026-08-13** — `deletion_protection = false` is already the shipped default on both `sync_metadata` tables (`google_bigquery_table.sync_metadata` and `.sync_metadata_test`), so there's nothing to touch there. The one remaining lock is `delete_contents_on_destroy`, which defaults to `false` on **both** BigQuery datasets — and both need it flipped, not just prod:

```hcl
# terraform/main.tf — change on BOTH of these:
resource "google_bigquery_dataset" "plex" {        # PlexProd
  delete_contents_on_destroy = true   # ← was false
}

resource "google_bigquery_dataset" "plex_test" {    # PlexTest
  delete_contents_on_destroy = true   # ← was false
}
```

Apply the change (this only updates the protection flags, nothing is deleted yet):

```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

---

## Step 3 — Delete Docker images from Artifact Registry

Terraform cannot delete a repository that still has images in it. Clear the images first:

```bash
# Delete the ETL image
gcloud artifacts docker images delete \
  us-central1-docker.pkg.dev/voxdatalake/plex-pipeline/etl \
  --delete-tags --quiet --project=voxdatalake

# Verify the repo is empty
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/voxdatalake/plex-pipeline \
  --project=voxdatalake
# Should return no rows
```

---

## Step 4 — Manual raw table cleanup (usually not needed)

Every `raw_*` table and report view is created by the ETL jobs at runtime, not by Terraform — dozens of them across both `PlexProd` and `PlexTest` now (one per `bq_table:`/`bq_view:` entry across all 8 `reports/*.yaml`). With `delete_contents_on_destroy = true` set on both datasets in Step 2, `terraform destroy` in Step 5 drops the datasets **and everything in them** — this step is redundant in the normal case.

Only do this manually if you want to empty a dataset **without** destroying it (e.g. testing a clean re-run without a full teardown):

```bash
bq rm -f voxdatalake:PlexTest.raw_Sales_v_PO   # example — repeat per table, or use `bq ls` to enumerate first
```

Or in GCP Console: **BigQuery** → the dataset → the table → three-dot menu → **Delete**.

---

## Step 5 — Destroy all Terraform resources

```bash
cd terraform
terraform destroy -var-file=terraform.tfvars
```

Type `yes` when prompted. This takes several minutes and removes everything Terraform created — **104 resources** as of 2026-08-13 (16 Cloud Run jobs + 32 Cloud Scheduler jobs + 2 BigQuery datasets + 5 secrets + the report-configs bucket + IAM/service-account resources + more), not the ~18 from the original single-job setup.

**Expected output at the end:**
```
Destroy complete! Resources: 104 destroyed.
```
(This number will drift as report families are added/removed — treat it as "roughly matches what `terraform state list | wc -l` showed before you started," not a literal constant.)

**Verify in GCP Console:**
- **Secret Manager** → all 5 secrets should be gone
- **Cloud Run** → **Jobs** → all 16 jobs should be gone
- **BigQuery** → both `PlexProd` and `PlexTest` datasets should be gone
- **Cloud Storage** → the `voxdatalake-report-configs` bucket should be gone
- **Artifact Registry** → `plex-pipeline` repo should be gone
- **IAM & Admin** → **Service Accounts** → `plex-etl-sa` should be gone

---

## Step 6 — Clean up the Terraform state bucket (optional, full teardown only)

Terraform state lives in a shared GCS backend (`gs://voxdatalake-terraform-state`), not a local file — there's nothing to clean up on your machine. A successful `terraform destroy` leaves that bucket's state object empty (no resources), which is fine to leave as-is if you might redeploy later.

The state bucket itself is **not** managed by Terraform (it's created manually, outside the config it stores — this avoids Terraform ever being able to delete the very bucket holding its own state). If you want to remove it too as part of a full teardown:

```bash
gcloud storage rm -r gs://voxdatalake-terraform-state --project=voxdatalake
```

Only do this if you're certain no one will need this project's Terraform history again.

---

## Redeploying to a new project

Once tearing down is complete, deploying to a different project is just updating one file and rerunning the same steps.

**1. Restore `main.tf`** to safe defaults (undo the one change from Step 2):

```hcl
# Revert on BOTH google_bigquery_dataset resources (plex and plex_test):
delete_contents_on_destroy = false   # back to false (protects data on future destroys)
```
`deletion_protection = false` on the `sync_metadata` tables was never changed — nothing to revert there.

**2. Update `terraform/terraform.tfvars`** with the new project and a real image tag:

```hcl
gcp_project = "your-new-project-id"
image_url   = "us-central1-docker.pkg.dev/your-new-project-id/plex-pipeline/etl:$SHA"   # never :latest
```

**3. Follow the normal deployment steps — this recreates the full 16-job stack, not one job:**

```bash
# Authenticate to new project
gcloud config set project your-new-project-id
gcloud auth application-default login

# Deploy infrastructure (creates all 16 jobs, referencing image_url above)
cd terraform
terraform init
terraform apply -var-file=terraform.tfvars

# Push the image to the new project's registry, tagged with a commit SHA
cd ..
gcloud auth configure-docker us-central1-docker.pkg.dev
SHA=$(git rev-parse --short HEAD)
docker build -t us-central1-docker.pkg.dev/your-new-project-id/plex-pipeline/etl:$SHA .
docker push us-central1-docker.pkg.dev/your-new-project-id/plex-pipeline/etl:$SHA

# Re-apply — this DOES set the image, but only because these jobs are
# brand new (lifecycle.ignore_changes only blocks changes to an EXISTING
# resource, not its value at creation). On any later rebuild, use
# `gcloud run jobs update JOB --image=...` instead — this step won't work again.
cd terraform
terraform apply -var-file=terraform.tfvars

# Add ALL FIVE secrets to the new project's Secret Manager
echo -n 'YOUR_PLEX_TOKEN'    | gcloud secrets versions add plex-access-token  --data-file=- --project=your-new-project-id
echo -n 'YOUR_SENDGRID_KEY'  | gcloud secrets versions add sendgrid-api-key   --data-file=- --project=your-new-project-id
echo -n 'YOUR_ODBC_USER'     | gcloud secrets versions add plex-odbc-user     --data-file=- --project=your-new-project-id
echo -n 'YOUR_ODBC_PASSWORD' | gcloud secrets versions add plex-odbc-password --data-file=- --project=your-new-project-id
echo -n 'YOUR_COMPANY_CODE'  | gcloud secrets versions add plex-company-code  --data-file=- --project=your-new-project-id

# Upload all 8 report YAML pairs + SQL files — see docs/DISASTER_RECOVERY.md
# for the full loop; nothing runs correctly until this step is done, since
# every job reads its config from GCS at runtime.

# Test each job — at minimum, loop the *-test variants
gcloud run jobs execute plex-etl-test --region=us-central1 --project=your-new-project-id --wait
```

See [QUICKSTART.md](QUICKSTART.md) for the full walkthrough (also corrected
2026-08-13 for the same 16-job reality) and
[DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) for the complete
secrets/report-config restore loop.
