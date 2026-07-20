# Infrastructure Teardown Guide

> Use this when you need to completely remove all GCP resources — for example, to redeploy to a different project, or to decommission the pipeline.
>
> **This is destructive and irreversible.** BigQuery data, Secret Manager versions, and Docker images will be permanently deleted.

---

## What gets deleted

| Resource | Managed by | Deleted how |
|---|---|---|
| Cloud Run job (`plex-etl`) | Terraform | `terraform destroy` |
| Cloud Scheduler job (`plex-daily-sync`) | Terraform | `terraform destroy` |
| BigQuery dataset (`PlexTest`) + all tables | Terraform | `terraform destroy` (after unlocking) |
| Artifact Registry repo (`plex-pipeline`) | Terraform | `terraform destroy` (after clearing images) |
| Secret Manager containers (4 secrets) | Terraform | `terraform destroy` |
| Secret versions (the actual token values) | Manual | Deleted with the container |
| Service account (`plex-etl-sa`) | Terraform | `terraform destroy` |
| IAM role bindings | Terraform | `terraform destroy` |
| GCP APIs enabled | Terraform | Left enabled (harmless, free) |
| Docker image layers | Manual | Must clear before destroy |
| `raw_Part_v_Part` BQ table | ETL job (not Terraform) | Must delete manually first |

---

## Step 1 — Pause the scheduler

Stop any new runs from starting while you tear things down:

```bash
gcloud scheduler jobs pause plex-daily-sync \
  --location=us-central1 --project=voxdatalake
```

---

## Step 2 — Unlock Terraform-protected resources

Two resources have deletion protection enabled. You must unlock them before `terraform destroy` can remove them.

Edit `terraform/main.tf` — make these two changes:

**Change 1** — allow the BigQuery dataset to be deleted even if it has tables:
```hcl
# Before
resource "google_bigquery_dataset" "plex" {
  dataset_id                 = var.bq_dataset
  location                   = var.bq_location
  delete_contents_on_destroy = false   # ← change this
}

# After
resource "google_bigquery_dataset" "plex" {
  dataset_id                 = var.bq_dataset
  location                   = var.bq_location
  delete_contents_on_destroy = true    # ← to this
}
```

**Change 2** — allow the sync_metadata table to be deleted:
```hcl
# Before
resource "google_bigquery_table" "sync_metadata" {
  dataset_id = google_bigquery_dataset.plex.dataset_id
  table_id   = var.metadata_table
  schema     = jsonencode([...])
}

# After — add deletion_protection = false
resource "google_bigquery_table" "sync_metadata" {
  dataset_id          = google_bigquery_dataset.plex.dataset_id
  table_id            = var.metadata_table
  deletion_protection = false   # ← add this line
  schema              = jsonencode([...])
}
```

Apply the changes (this only updates the protection flags, nothing is deleted yet):

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

## Step 4 — Delete the raw_Part_v_Part table

The `raw_Part_v_Part` table is created by the ETL job loading data, not by Terraform, so `terraform destroy` won't touch it. Delete it manually first so the dataset can be dropped:

```bash
bq rm -f voxdatalake:PlexTest.raw_Part_v_Part
```

Or in GCP Console: **BigQuery** → `PlexTest` → `raw_Part_v_Part` → three-dot menu → **Delete**.

---

## Step 5 — Destroy all Terraform resources

```bash
cd terraform
terraform destroy -var-file=terraform.tfvars
```

Type `yes` when prompted. This takes 2–4 minutes and removes everything Terraform created.

**Expected output at the end:**
```
Destroy complete! Resources: 18 destroyed.
```

**Verify in GCP Console:**
- **Secret Manager** → the 4 plex secrets should be gone
- **Cloud Run** → **Jobs** → `plex-etl` should be gone
- **BigQuery** → `PlexTest` dataset should be gone
- **Artifact Registry** → `plex-pipeline` repo should be gone
- **IAM & Admin** → **Service Accounts** → `plex-etl-sa` should be gone

---

## Step 6 — Clean up local state files

The Terraform state files on your machine now describe a destroyed world. Remove them so they don't cause confusion when redeploying:

```bash
cd terraform
rm terraform.tfstate terraform.tfstate.backup
```

---

## Redeploying to a new project

Once tearing down is complete, deploying to a different project is just updating one file and rerunning the same steps.

**1. Restore `main.tf`** to safe defaults (undo the changes from Step 2):

```hcl
# Revert these two lines:
delete_contents_on_destroy = false   # back to false (protects prod data)
# Remove deletion_protection = false from sync_metadata (or set to true)
```

**2. Update `terraform/terraform.tfvars`** with the new project:

```hcl
gcp_project = "your-new-project-id"
image_url   = "us-central1-docker.pkg.dev/your-new-project-id/plex-pipeline/etl:latest"
```

**3. Follow the normal deployment steps:**

```bash
# Authenticate to new project
gcloud config set project your-new-project-id
gcloud auth application-default login

# Deploy infrastructure
cd terraform
terraform init
terraform apply -var-file=terraform.tfvars

# Push the image to the new project's registry
cd ..
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build -t us-central1-docker.pkg.dev/your-new-project-id/plex-pipeline/etl:latest .
docker push us-central1-docker.pkg.dev/your-new-project-id/plex-pipeline/etl:latest

# Re-apply so Cloud Run picks up the real image
cd terraform
terraform apply -var-file=terraform.tfvars

# Add the Plex token to the new project's Secret Manager
echo -n 'YOUR_PLEX_TOKEN' | gcloud secrets versions add plex-access-token \
  --data-file=- --project=your-new-project-id

# Test the job
gcloud run jobs execute plex-etl --region=us-central1 --project=your-new-project-id --wait
```

See [QUICKSTART.md](QUICKSTART.md) for the full walkthrough.
