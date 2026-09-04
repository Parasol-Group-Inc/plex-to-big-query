# Disaster Recovery — "the GCP account is lost, now what?"

> Two very different scenarios hide behind that question. Read the first
> paragraph of each section to figure out which one you're in.

---

## Scenario A — Emilio's personal Google account is lost/inaccessible

(Forgotten password, disabled 2FA device, account compromised, offboarded,
etc. — but the **GCP project `voxdatalake` itself still exists**.)

**This is fully recoverable — confirmed 2026-07-20.** A second human already
holds `roles/owner` on the project:

```
roles/owner   user:emilio.dominguez@parasolgroupinc.com
roles/owner   user:jennilyn.tockstein@parasolgroupinc.com
```

If Emilio's account is ever lost, Jennilyn can grant a replacement person
Owner/Editor access immediately in IAM & Admin → IAM — no Google Workspace
Super Admin or org-level recovery needed. Re-check this periodically
(people leave, roles get cleaned up):

```bash
gcloud projects get-iam-policy voxdatalake --format="table(bindings.role,bindings.members)" --flatten="bindings[]" | grep -i "owner\|editor"
```

If this ever comes back showing only one Owner, add a second one before it
becomes urgent.

---

## Scenario B — the entire GCP project is deleted or unrecoverable

(Billing lapses and Google deletes the project after the grace period,
accidental `gcloud projects delete`, or Scenario A above with no org
backstop.) This is the "truly start from zero" case, and it's where the
gaps actually are. Here's what's recoverable vs. not, as of 2026-07-20:

| Asset | Recoverable? | From where |
|---|---|---|
| All application code, Terraform config, docs | ✅ Yes | git (GitHub) |
| Terraform state | ⚠ Partially | Was in `gs://voxdatalake-terraform-state` — gone if the project is deleted. But the state file mainly records *what exists*, not secret values, so losing it just means re-`import`-ing or re-`apply`-ing into a fresh project (see Step 3 below) |
| `terraform.tfvars` (real values: emails, view names, etc.) | ⚠ Partially | Gitignored by design (correct — never commit it). The **only** other copy is on Emilio's machine. **Gap: back this up somewhere durable** (password manager, encrypted note) since it's not secret material but is needed to reconstruct config quickly |
| Plex IAM access token, ODBC password, company code, SendGrid API key (actual secret **values**) | ❌ Not from GCP | Only in Secret Manager, gone with the project. The Plex token can be regenerated from the Plex portal if Plex account access still exists. SendGrid key can be regenerated from the SendGrid account. **Gap: no backup of the current values outside GCP** |
| Plex ODBC driver + applied license (`OAODBC64.LIC`) | ⚠ Partially | Currently in `gs://voxdatalake-build-assets` (gone with the project) AND locally in Emilio's `driver/`+`zipfiles/` folders (gitignored, this machine only). **Gap: no off-GCP, off-laptop backup** of the licensed driver or the original vendor packages. Re-obtaining requires re-running the full `docs/APPLY_DRIVER_LICENSE.md` process from a fresh Plex-support-provided driver package plus the license serial/key (`004193623`/`35057920` — also only recorded in this repo's docs and Emilio's local `zipfiles/`) |

### Closing the gaps (recommended, doesn't require an emergency to do now)

1. Add a second GCP Owner (Scenario A, above).
2. Put a copy of `terraform.tfvars`, the actual secret values, and the
   driver license serial/key into a shared password manager or secure vault
   the whole team can access — not just this laptop.
3. Upload the vendor driver packages (`zipfiles/*.tar`) and the licensed
   `driver/` folder (with `OAODBC64.LIC`) to that same durable location, or
   at minimum to a second GCS bucket in a *different* GCP project so a
   single project deletion can't take out both copies.

### Bootstrap runbook (once the gaps above are closed, or you're doing this proactively to test the process)

```bash
# 1. Create the project
gcloud projects create NEW-PROJECT-ID --name="Plex to BigQuery"
gcloud config set project NEW-PROJECT-ID
# Link billing in Console: Billing → link a billing account

# 2. Recreate the Terraform state bucket (outside Terraform's own management)
gcloud storage buckets create gs://NEW-PROJECT-ID-terraform-state \
  --project=NEW-PROJECT-ID --location=us-central1 --uniform-bucket-level-access
gcloud storage buckets update gs://NEW-PROJECT-ID-terraform-state --versioning

# 3. Recreate the build-assets bucket and restore the driver+license
gcloud storage buckets create gs://NEW-PROJECT-ID-build-assets --project=NEW-PROJECT-ID
gcloud storage cp -r <your backed-up driver/ folder>/* \
  gs://NEW-PROJECT-ID-build-assets/plex-odbc-driver/
# If you don't have a backed-up driver/, see docs/APPLY_DRIVER_LICENSE.md
# to re-license from a fresh Plex-support-provided driver package.

# 4. Point Terraform at the new project + new state bucket
cd terraform
# Edit main.tf's backend block: bucket = "NEW-PROJECT-ID-terraform-state"
cp terraform.tfvars.example terraform.tfvars
# Fill in terraform.tfvars from your backed-up copy (or reconstruct from
# docs/CLICKUP_TEAM_GUIDE.md's documented live values), pointing
# gcp_project at NEW-PROJECT-ID
terraform init
terraform apply -var-file=terraform.tfvars

# 5. Restore ALL FIVE secret VALUES (from your backed-up copies, not from
# GCP -- they're gone). Missing any one of these will make its owning job(s)
# fail credential fetch.
echo -n 'PLEX_TOKEN'      | gcloud secrets versions add plex-access-token  --data-file=- --project=NEW-PROJECT-ID
echo -n 'SENDGRID_KEY'    | gcloud secrets versions add sendgrid-api-key   --data-file=- --project=NEW-PROJECT-ID
echo -n 'ODBC_USER'       | gcloud secrets versions add plex-odbc-user     --data-file=- --project=NEW-PROJECT-ID
echo -n 'ODBC_PASSWORD'   | gcloud secrets versions add plex-odbc-password --data-file=- --project=NEW-PROJECT-ID
echo -n 'COMPANY_CODE'    | gcloud secrets versions add plex-company-code  --data-file=- --project=NEW-PROJECT-ID

# 6. Build and push the image (driver must be in driver/ locally, from
# the build-assets bucket restored in step 3). Tag with a commit SHA, never
# ":latest" — set that SHA as image_url in terraform.tfvars before the
# re-apply below.
gcloud storage cp -r gs://NEW-PROJECT-ID-build-assets/plex-odbc-driver/* driver/
SHA=$(git rev-parse --short HEAD)
docker build -t us-central1-docker.pkg.dev/NEW-PROJECT-ID/plex-pipeline/etl:$SHA .
docker push us-central1-docker.pkg.dev/NEW-PROJECT-ID/plex-pipeline/etl:$SHA
# Update terraform.tfvars: image_url = ".../etl:$SHA"
terraform apply -var-file=terraform.tfvars
# This apply DOES set the image — every job's `lifecycle { ignore_changes }`
# only blocks CHANGES to an already-existing resource, not its initial
# value at creation. On any LATER rebuild, this step stops working and you
# need an explicit `gcloud run jobs update JOB --image=...` per job instead
# (or deploy/cloudbuild.yaml's deploy-all step) — see docs/TROUBLESHOOTING.md
# § "Full rebuild procedure."

# 7. Upload ALL 8 report YAML pairs + SQL files — these ARE in git, in reports/
for report in sales_orders work_orders purchasing_open_orders part_obsolescence \
              inventory_activity inventory_snapshot quality_nonconformance part_on_hand_inventory; do
  gcloud storage cp "reports/${report}.yaml" "gs://NEW-PROJECT-ID-report-configs/reports/"
  gcloud storage cp "reports/test/${report}.yaml" "gs://NEW-PROJECT-ID-report-configs/test/"
done
gcloud storage cp reports/sql/*.sql gs://NEW-PROJECT-ID-report-configs/sql/

# 8. Test before trusting it — loop all 8 *-test jobs, not just one
for job in plex-etl-sales-orders-test plex-etl-work-orders-test plex-etl-purchasing-open-orders-test \
           plex-etl-part-obsolescence-test plex-etl-inventory-activity-test \
           plex-etl-inventory-snapshot-test plex-etl-quality-nonconformance-test \
           plex-etl-part-on-hand-inventory-test; do
  gcloud run jobs execute "$job" --region=us-central1 --project=NEW-PROJECT-ID --wait
done
```

Everything in steps 1, 2, 4 (config), 7, and 8 comes entirely from git —
zero dependency on any one person or machine. Steps 3, 5, and 6 are the
parts that currently depend on backups that don't yet exist outside this
laptop — closing those three gaps is the real work, not writing this
runbook.

**One more thing not in the table above:** `terraform.tfvars` itself
(gitignored, local-only) is backed up to
`gs://voxdatalake-terraform-state/plex-to-big-query/terraform.tfvars.backup`
— same bucket as Terraform state, so it survives exactly as well as state
does (gone if the whole project is deleted, fine if only Emilio's laptop
is lost). Re-upload it after every edit; see the file's own header for the
command.
