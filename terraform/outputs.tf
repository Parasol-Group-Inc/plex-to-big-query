# ── Service account ───────────────────────────────────────────────────────────
output "service_account_email" {
  description = "Email of the ETL service account. Use when granting additional IAM roles."
  value       = google_service_account.etl.email
}

# ── Artifact Registry ─────────────────────────────────────────────────────────
output "artifact_registry_url" {
  description = "Base URL of the Artifact Registry repository."
  value       = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project}/${var.artifact_registry_repo}"
}

output "image_push_commands" {
  description = "Copy-paste commands to build, tag, and push the Docker image."
  value       = <<-EOT
    docker build -t ${var.gcp_region}-docker.pkg.dev/${var.gcp_project}/${var.artifact_registry_repo}/etl:latest .
    docker push ${var.gcp_region}-docker.pkg.dev/${var.gcp_project}/${var.artifact_registry_repo}/etl:latest
  EOT
}

# ── BigQuery ──────────────────────────────────────────────────────────────────
output "bigquery_dataset_id" {
  description = "Full BigQuery dataset reference."
  value       = "${var.gcp_project}.${google_bigquery_dataset.plex.dataset_id}"
}

output "bigquery_metadata_table" {
  description = "Full reference to the sync metadata table."
  value       = "${var.gcp_project}.${google_bigquery_dataset.plex.dataset_id}.${google_bigquery_table.sync_metadata.table_id}"
}

# ── Secret Manager ────────────────────────────────────────────────────────────
output "secret_names" {
  description = "The three Secret Manager secrets that need values added after apply."
  value = {
    odbc_user     = google_secret_manager_secret.odbc_user.secret_id
    odbc_password = google_secret_manager_secret.odbc_password.secret_id
    company_code  = google_secret_manager_secret.company_code.secret_id
  }
}

output "secret_version_commands" {
  description = "Copy-paste gcloud commands to populate secrets after terraform apply. Replace the placeholder values."
  value       = <<-EOT
    echo -n 'YOUR_PLEX_USER'     | gcloud secrets versions add ${google_secret_manager_secret.odbc_user.secret_id}     --data-file=- --project=${var.gcp_project}
    echo -n 'YOUR_PLEX_PASSWORD' | gcloud secrets versions add ${google_secret_manager_secret.odbc_password.secret_id} --data-file=- --project=${var.gcp_project}
    echo -n 'YOUR_COMPANY_CODE'  | gcloud secrets versions add ${google_secret_manager_secret.company_code.secret_id}  --data-file=- --project=${var.gcp_project}
  EOT
}

# ── Cloud Run ─────────────────────────────────────────────────────────────────
output "cloud_run_job_name" {
  description = "Cloud Run job name."
  value       = google_cloud_run_v2_job.etl.name
}

output "cloud_run_execute_command" {
  description = "Copy-paste command to trigger a manual job execution."
  value       = "gcloud run jobs execute ${google_cloud_run_v2_job.etl.name} --region=${var.gcp_region} --project=${var.gcp_project} --wait"
}

# ── Cloud Scheduler ───────────────────────────────────────────────────────────
output "scheduler_job_name" {
  description = "Cloud Scheduler job name and cron schedule."
  value       = "${google_cloud_scheduler_job.etl.name} — schedule: ${var.scheduler_cron} ${var.scheduler_time_zone}"
}

# ── Test environment ───────────────────────────────────────────────────────────
output "test_bigquery_dataset_id" {
  description = "Full BigQuery dataset reference for test pipeline."
  value       = "${var.gcp_project}.${google_bigquery_dataset.plex_test.dataset_id}"
}

output "test_cloud_run_execute_command" {
  description = "Copy-paste command to trigger a manual test job execution."
  value       = "gcloud run jobs execute ${google_cloud_run_v2_job.etl_test.name} --region=${var.gcp_region} --project=${var.gcp_project} --wait"
}

output "test_scheduler_job_name" {
  description = "Test Cloud Scheduler job name and cron schedule."
  value       = "${google_cloud_scheduler_job.etl_test.name} — schedule: ${var.scheduler_cron_test} ${var.scheduler_time_zone}"
}
