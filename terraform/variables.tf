variable "gcp_project" {
  type        = string
  description = "GCP project ID"
}

variable "gcp_region" {
  type        = string
  description = "GCP region for Cloud Run and Scheduler"
  default     = "us-central1"
}

variable "bq_dataset" {
  type        = string
  description = "BigQuery dataset name"
}

variable "bq_location" {
  type        = string
  description = "BigQuery dataset location"
  default     = "US"
}

variable "bq_table" {
  type        = string
  description = "Target BigQuery table name"
}

variable "metadata_table" {
  type        = string
  description = "Metadata table name"
  default     = "sync_metadata"
}

variable "plex_host" {
  type        = string
  description = "Plex ODBC hostname (vox.odbc.plex.com for prod, vox.test.odbc.plex.com for test)"
  default     = "vox.odbc.plex.com"
}

variable "plex_odbc_user" {
  type        = string
  description = "Plex login in username.company format (e.g. edominguez.parasol)"
}

variable "plex_dsn" {
  type        = string
  description = "ODBC DSN name — used for username/password auth fallback only"
  default     = "PlexProduction"
}

variable "secret_access_token" {
  type        = string
  description = "Secret Manager secret name for the Plex IAM access token"
  default     = "plex-access-token"
}

variable "backfill_minutes" {
  type        = number
  description = "Backfill window in minutes"
  default     = 5
}

variable "secret_odbc_user" {
  type        = string
  description = "Secret Manager secret name for ODBC username"
  default     = "plex-odbc-user"
}

variable "secret_odbc_password" {
  type        = string
  description = "Secret Manager secret name for ODBC password"
  default     = "plex-odbc-password"
}

variable "secret_company_code" {
  type        = string
  description = "Secret Manager secret name for CompanyCode"
  default     = "plex-company-code"
}

variable "cloud_run_job" {
  type        = string
  description = "Cloud Run job name"
  default     = "plex-etl"
}

variable "scheduler_job" {
  type        = string
  description = "Cloud Scheduler job name"
  default     = "plex-daily-sync"
}

variable "scheduler_cron" {
  type        = string
  description = "Cron schedule"
  default     = "0 2 * * *"
}

variable "scheduler_time_zone" {
  type        = string
  description = "Scheduler time zone"
  default     = "UTC"
}

variable "service_account_name" {
  type        = string
  description = "Service account name (without domain)"
  default     = "plex-etl-sa"
}

variable "artifact_registry_repo" {
  type        = string
  description = "Artifact Registry repository name"
  default     = "plex-pipeline"
}

variable "image_url" {
  type        = string
  description = "Full container image URL in Artifact Registry"
}

# ── Plex query config ─────────────────────────────────────────────────────────

variable "plex_view" {
  type        = string
  description = "Plex view or stored procedure name to query (e.g. Part_v_Part)"
  default     = "Part_v_Part"
}

variable "plex_filter" {
  type        = string
  description = "SQL WHERE clause to apply (include the word WHERE, or leave empty for all rows)"
  default     = "WHERE Part_Type = 'Raw Materials'"
}

variable "plex_date_col" {
  type        = string
  description = "Timestamp column name for incremental sync. Leave empty for full refresh."
  default     = ""
}

# ── Email reporting ───────────────────────────────────────────────────────────

variable "sendgrid_enabled" {
  type        = string
  description = "Set to 'true' to enable email reports after each run"
  default     = "false"
}

variable "report_from_email" {
  type        = string
  description = "Verified sender email address in SendGrid"
  default     = ""
}

variable "report_to_emails" {
  type        = string
  description = "Comma-separated list of report recipient emails"
  default     = ""
}

variable "report_subject" {
  type        = string
  description = "Email subject line for run reports"
  default     = "Plex to BigQuery ETL Report"
}

variable "secret_sendgrid_key" {
  type        = string
  description = "Secret Manager secret name for the SendGrid API key"
  default     = "sendgrid-api-key"
}

variable "company_name" {
  type        = string
  description = "Company name shown in email subject line: [Plex ETL] STATUS — {company_name} — DATE"
  default     = "Parasol"
}

# ── Test environment ──────────────────────────────────────────────────────────

variable "plex_host_test" {
  type        = string
  description = "Test Plex ODBC hostname"
  default     = "vox.test.odbc.plex.com"
}

variable "bq_dataset_test" {
  type        = string
  description = "BigQuery dataset for the test pipeline"
  default     = "PlexTest"
}

variable "cloud_run_job_test" {
  type        = string
  description = "Cloud Run job name for the test pipeline"
  default     = "plex-etl-test"
}

variable "scheduler_job_test" {
  type        = string
  description = "Cloud Scheduler job name for the test pipeline"
  default     = "plex-daily-sync-test"
}

variable "scheduler_cron_test" {
  type        = string
  description = "Cron schedule for the test pipeline (offset from prod to avoid overlap)"
  default     = "0 3 * * *"
}

# ── Report config (GCS-backed, editable without deployment) ───────────────────

variable "report_configs_bucket" {
  type        = string
  description = "GCS bucket name for report configuration YAML files and SQL view definitions"
  default     = ""
}

variable "report_config_gcs_path" {
  type        = string
  description = "GCS URI of the report config YAML for the production Cloud Run job (gs://bucket/path)"
  default     = ""
}

variable "report_config_gcs_path_test" {
  type        = string
  description = "GCS URI of the report config YAML for the test Cloud Run job (gs://bucket/path)"
  default     = ""
}

# ── Failure retry (all 4 jobs) ─────────────────────────────────────────────────

variable "retry_scheduler_cron" {
  type        = string
  description = "Cron schedule for the failure-retry trigger — fires daily regardless; the job itself no-ops if today's scheduled run already succeeded/partial"
  default     = "0 6 * * *"
}

variable "retry_time_zone" {
  type        = string
  description = "Time zone for the retry scheduler (IANA name — Cloud Scheduler handles DST automatically)"
  default     = "America/Denver"
}
