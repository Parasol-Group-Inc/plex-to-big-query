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
  description = "Plex ODBC hostname (odbc.plex.com for prod, vox.odbc.plex.com for test)"
  default     = "odbc.plex.com"
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
