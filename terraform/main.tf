terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
  }

  # Shared remote state so any team member can safely run plan/apply --
  # state is no longer tied to a single machine. Bucket is created outside
  # this config (gcloud storage buckets create) so `terraform destroy`
  # can never delete the bucket holding its own state. Versioning is on --
  # to roll back, restore a prior object generation and re-init.
  backend "gcs" {
    bucket = "voxdatalake-terraform-state"
    prefix = "plex-to-big-query"
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.gcp_region
}

data "google_project" "current" {
  project_id = var.gcp_project
}

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "bigquery.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "storage.googleapis.com",
  ])

  project            = var.gcp_project
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "etl" {
  account_id   = var.service_account_name
  display_name = "Plex ETL Service Account"
  description  = "Used by the Plex to BigQuery Cloud Run job"
}

resource "google_project_iam_member" "etl_roles" {
  for_each = toset([
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/secretmanager.secretAccessor",
    "roles/artifactregistry.reader",
    "roles/run.invoker",
  ])

  project = var.gcp_project
  role    = each.value
  member  = "serviceAccount:${google_service_account.etl.email}"
}

resource "google_service_account_iam_member" "scheduler_token_creator" {
  service_account_id = google_service_account.etl.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
}

# ── Report config bucket — edit YAML/SQL files here to change reports ─────────

resource "google_storage_bucket" "report_configs" {
  name                        = var.report_configs_bucket
  location                    = var.bq_location
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.required]
}

# Grant the ETL service account read access to the config bucket
resource "google_storage_bucket_iam_member" "etl_config_reader" {
  bucket = google_storage_bucket.report_configs.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.etl.email}"
}

# Upload initial report config files (Terraform manages the initial copy only).
# After initial setup, edit files directly in GCS Console or via:
#   gcloud storage cp reports/sales_orders.yaml gs://${var.report_configs_bucket}/reports/
#   gcloud storage cp reports/sql/sales_orders_view.sql gs://${var.report_configs_bucket}/sql/

resource "google_storage_bucket_object" "sales_orders_config_prod" {
  name         = "reports/sales_orders.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sales_orders.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "sales_orders_config_test" {
  name         = "test/sales_orders.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/test/sales_orders.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "sales_orders_view_sql" {
  name         = "sql/sales_orders_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_orders_view.sql"
  content_type = "text/plain"
}

resource "google_bigquery_dataset" "plex" {
  dataset_id                 = var.bq_dataset
  location                   = var.bq_location
  delete_contents_on_destroy = false
}

resource "google_artifact_registry_repository" "etl" {
  location      = var.gcp_region
  repository_id = var.artifact_registry_repo
  format        = "DOCKER"
  description   = "Plex ETL Docker images"
}

resource "google_bigquery_table" "sync_metadata" {
  dataset_id          = google_bigquery_dataset.plex.dataset_id
  table_id            = var.metadata_table
  deletion_protection = false

  schema = jsonencode([
    {
      name = "table_name"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "last_sync_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    },
    {
      name = "max_modified_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    },
    {
      name = "rows_written"
      type = "INTEGER"
      mode = "REQUIRED"
    },
    {
      name = "synced_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    }
  ])
}

# IAM token auth — primary secret
resource "google_secret_manager_secret" "access_token" {
  secret_id = var.secret_access_token
  replication {
    auto {}
  }
}

# SendGrid API key — optional, only needed when SENDGRID_ENABLED=true
resource "google_secret_manager_secret" "sendgrid_api_key" {
  secret_id = var.secret_sendgrid_key
  replication {
    auto {}
  }
}

# Username/password auth — kept for fallback / future use
resource "google_secret_manager_secret" "odbc_user" {
  secret_id = var.secret_odbc_user
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "odbc_password" {
  secret_id = var.secret_odbc_password
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "company_code" {
  secret_id = var.secret_company_code
  replication {
    auto {}
  }
}

resource "google_cloud_run_v2_job" "etl" {
  name     = var.cloud_run_job
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        # Plex connection — IAM auth
        env {
          name  = "PLEX_HOST"
          value = var.plex_host
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        # Plex connection — username/password auth (fallback)
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        # Report config — GCS path to the YAML that defines which views to extract.
        # Edit the YAML in GCS to change queries/filters without redeployment.
        # Leave empty to fall back to legacy single-view mode (PLEX_VIEW below).
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = var.report_config_gcs_path
        }
        # Legacy single-view config (used when REPORT_CONFIG_GCS_PATH is empty)
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        # Sync config
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        # Email reporting (optional — leave SENDGRID_ENABLED=false to disable)
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl" {
  name        = var.scheduler_job
  description = "Triggers Plex to BigQuery ETL job"
  schedule    = var.scheduler_cron
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# Retries the same job if today's scheduled run failed. Fires every day at
# the same time regardless — main.py checks job_run_log and no-ops if
# today's scheduled run already succeeded/partial.
resource "google_cloud_scheduler_job" "etl_retry" {
  name        = "${var.scheduler_job}-retry"
  description = "Retries the sales orders ETL job if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ── Test environment ── same image, test Plex host, PlexTest dataset ──────────

resource "google_bigquery_dataset" "plex_test" {
  dataset_id                 = var.bq_dataset_test
  location                   = var.bq_location
  delete_contents_on_destroy = false
}

resource "google_bigquery_table" "sync_metadata_test" {
  dataset_id          = google_bigquery_dataset.plex_test.dataset_id
  table_id            = var.metadata_table
  deletion_protection = false

  schema = jsonencode([
    {
      name = "table_name"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "last_sync_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    },
    {
      name = "max_modified_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    },
    {
      name = "rows_written"
      type = "INTEGER"
      mode = "REQUIRED"
    },
    {
      name = "synced_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    }
  ])
}

resource "google_cloud_run_v2_job" "etl_test" {
  name     = var.cloud_run_job_test
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset_test
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        # Plex connection — IAM auth (test host)
        env {
          name  = "PLEX_HOST"
          value = var.plex_host_test
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        # Plex connection — username/password auth (fallback)
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        # Report config — GCS path to the YAML that defines which views to extract
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = var.report_config_gcs_path_test
        }
        # Legacy single-view config (used when REPORT_CONFIG_GCS_PATH is empty)
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        # Sync config
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        # Email reporting
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_test" {
  name        = var.scheduler_job_test
  description = "Triggers Plex to BigQuery ETL job (test)"
  schedule    = var.scheduler_cron_test
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_test.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

resource "google_cloud_scheduler_job" "etl_test_retry" {
  name        = "${var.scheduler_job_test}-retry"
  description = "Retries the sales orders ETL job (test) if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_test.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ── Work Orders report — GCS config files ─────────────────────────────────────

resource "google_storage_bucket_object" "work_orders_config_prod" {
  name         = "reports/work_orders.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/work_orders.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "work_orders_config_test" {
  name         = "test/work_orders.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/test/work_orders.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "work_orders_view_sql" {
  name         = "sql/work_orders_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/work_orders_view.sql"
  content_type = "text/plain"
}

# ── Work Orders report — prod (PlexProd, 4 AM UTC) ───────────────────────────

resource "google_cloud_run_v2_job" "etl_work_orders" {
  name     = "plex-etl-work-orders"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/reports/work_orders.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_work_orders" {
  name        = "plex-work-orders-sync"
  description = "Triggers Plex to BigQuery work orders ETL job"
  schedule    = "20 19 * * *" # 7:20 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_work_orders.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

resource "google_cloud_scheduler_job" "etl_work_orders_retry" {
  name        = "plex-work-orders-sync-retry"
  description = "Retries the work orders ETL job if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_work_orders.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ── Work Orders report — test (PlexTest, 5 AM UTC) ───────────────────────────

resource "google_cloud_run_v2_job" "etl_work_orders_test" {
  name     = "plex-etl-work-orders-test"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset_test
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host_test
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/test/work_orders.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_work_orders_test" {
  name        = "plex-work-orders-sync-test"
  description = "Triggers Plex to BigQuery work orders ETL job (test)"
  schedule    = "30 19 * * *" # 7:30 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_work_orders_test.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

resource "google_cloud_scheduler_job" "etl_work_orders_test_retry" {
  name        = "plex-work-orders-sync-test-retry"
  description = "Retries the work orders ETL job (test) if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_work_orders_test.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ═══════════════════════════════════════════════════════════════════════════
# NetSuite parity reports (docs/NETSUITE_REPORT_BUILD_PLAN.md) — added 2026-08-10/11
#
# All 4 reports below (Purchasing Open Orders, Part Obsolescence, Inventory
# Activity, Inventory Snapshot/Valuation Summary) are live. The first three
# use a single bq_view mapping and were deployed 2026-08-10 against the
# then-current image. Inventory Snapshot's report.yaml has a LIST-form
# bq_view (2 views from 1 extraction run) — deployment was held until the
# new main.py (bq_view_configs/validate_bq_view) was built, pushed, and
# smoke-tested via Cloud Build on 2026-08-11.
# ═══════════════════════════════════════════════════════════════════════════

# ── Purchasing Open Orders report — GCS config files ─────────────────────────

resource "google_storage_bucket_object" "purchasing_open_orders_config_prod" {
  name         = "reports/purchasing_open_orders.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/purchasing_open_orders.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "purchasing_open_orders_config_test" {
  name         = "test/purchasing_open_orders.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/test/purchasing_open_orders.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "purchasing_open_orders_view_sql" {
  name         = "sql/purchasing_open_orders_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/purchasing_open_orders_view.sql"
  content_type = "text/plain"
}

# ── Purchasing Open Orders — prod (PlexProd, 6 AM UTC) ───────────────────────

resource "google_cloud_run_v2_job" "etl_purchasing_open_orders" {
  name     = "plex-etl-purchasing-open-orders"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/reports/purchasing_open_orders.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_purchasing_open_orders" {
  name        = "plex-purchasing-open-orders-sync"
  description = "Triggers Plex to BigQuery purchasing open orders ETL job"
  schedule    = "40 19 * * *" # 7:40 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_purchasing_open_orders.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

resource "google_cloud_scheduler_job" "etl_purchasing_open_orders_retry" {
  name        = "plex-purchasing-open-orders-sync-retry"
  description = "Retries the purchasing open orders ETL job if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_purchasing_open_orders.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ── Purchasing Open Orders — test (PlexTest, 7 AM UTC) ───────────────────────

resource "google_cloud_run_v2_job" "etl_purchasing_open_orders_test" {
  name     = "plex-etl-purchasing-open-orders-test"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset_test
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host_test
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/test/purchasing_open_orders.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_purchasing_open_orders_test" {
  name        = "plex-purchasing-open-orders-sync-test"
  description = "Triggers Plex to BigQuery purchasing open orders ETL job (test)"
  schedule    = "50 19 * * *" # 7:50 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_purchasing_open_orders_test.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

resource "google_cloud_scheduler_job" "etl_purchasing_open_orders_test_retry" {
  name        = "plex-purchasing-open-orders-sync-test-retry"
  description = "Retries the purchasing open orders ETL job (test) if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_purchasing_open_orders_test.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ── Part Obsolescence report — GCS config files ──────────────────────────────

resource "google_storage_bucket_object" "part_obsolescence_config_prod" {
  name         = "reports/part_obsolescence.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/part_obsolescence.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "part_obsolescence_config_test" {
  name         = "test/part_obsolescence.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/test/part_obsolescence.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "part_obsolescence_view_sql" {
  name         = "sql/part_obsolescence_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/part_obsolescence_view.sql"
  content_type = "text/plain"
}

# ── Part Obsolescence — prod (PlexProd, 8 AM UTC) ─────────────────────────────

resource "google_cloud_run_v2_job" "etl_part_obsolescence" {
  name     = "plex-etl-part-obsolescence"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/reports/part_obsolescence.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_part_obsolescence" {
  name        = "plex-part-obsolescence-sync"
  description = "Triggers Plex to BigQuery part obsolescence ETL job"
  schedule    = "0 20 * * *" # 8:00 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_part_obsolescence.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

resource "google_cloud_scheduler_job" "etl_part_obsolescence_retry" {
  name        = "plex-part-obsolescence-sync-retry"
  description = "Retries the part obsolescence ETL job if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_part_obsolescence.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ── Part Obsolescence — test (PlexTest, 9 AM UTC) ─────────────────────────────

resource "google_cloud_run_v2_job" "etl_part_obsolescence_test" {
  name     = "plex-etl-part-obsolescence-test"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset_test
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host_test
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/test/part_obsolescence.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_part_obsolescence_test" {
  name        = "plex-part-obsolescence-sync-test"
  description = "Triggers Plex to BigQuery part obsolescence ETL job (test)"
  schedule    = "10 20 * * *" # 8:10 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_part_obsolescence_test.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

resource "google_cloud_scheduler_job" "etl_part_obsolescence_test_retry" {
  name        = "plex-part-obsolescence-sync-test-retry"
  description = "Retries the part obsolescence ETL job (test) if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_part_obsolescence_test.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ── Inventory Activity report — GCS config files ─────────────────────────────

resource "google_storage_bucket_object" "inventory_activity_config_prod" {
  name         = "reports/inventory_activity.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/inventory_activity.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "inventory_activity_config_test" {
  name         = "test/inventory_activity.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/test/inventory_activity.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "inventory_activity_view_sql" {
  name         = "sql/inventory_activity_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/inventory_activity_view.sql"
  content_type = "text/plain"
}

# ── Inventory Activity — prod (PlexProd, 10 AM UTC) ───────────────────────────

resource "google_cloud_run_v2_job" "etl_inventory_activity" {
  name     = "plex-etl-inventory-activity"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/reports/inventory_activity.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_inventory_activity" {
  name        = "plex-inventory-activity-sync"
  description = "Triggers Plex to BigQuery inventory activity ETL job"
  schedule    = "20 20 * * *" # 8:20 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_inventory_activity.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

resource "google_cloud_scheduler_job" "etl_inventory_activity_retry" {
  name        = "plex-inventory-activity-sync-retry"
  description = "Retries the inventory activity ETL job if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_inventory_activity.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ── Inventory Activity — test (PlexTest, 11 AM UTC) ───────────────────────────

resource "google_cloud_run_v2_job" "etl_inventory_activity_test" {
  name     = "plex-etl-inventory-activity-test"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset_test
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host_test
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/test/inventory_activity.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_inventory_activity_test" {
  name        = "plex-inventory-activity-sync-test"
  description = "Triggers Plex to BigQuery inventory activity ETL job (test)"
  schedule    = "30 20 * * *" # 8:30 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_inventory_activity_test.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

resource "google_cloud_scheduler_job" "etl_inventory_activity_test_retry" {
  name        = "plex-inventory-activity-sync-test-retry"
  description = "Retries the inventory activity ETL job (test) if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_inventory_activity_test.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}

# ═══════════════════════════════════════════════════════════════════════════
# Inventory Snapshot / Valuation Summary report. Its report.yaml has a
# list-form bq_view (2 views from 1 extraction run) — requires the bq_view-
# list support in main.py (bq_view_configs/validate_bq_view). Enabled
# 2026-08-11 after that main.py was built, pushed, and deployed to
# plex-etl/plex-etl-test via Cloud Build (smoke test passed).
# ═══════════════════════════════════════════════════════════════════════════

resource "google_storage_bucket_object" "inventory_snapshot_config_prod" {
  name         = "reports/inventory_snapshot.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/inventory_snapshot.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "inventory_snapshot_config_test" {
  name         = "test/inventory_snapshot.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/test/inventory_snapshot.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "inventory_snapshot_view_sql" {
  name         = "sql/inventory_snapshot_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/inventory_snapshot_view.sql"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "inventory_valuation_summary_view_sql" {
  name         = "sql/inventory_valuation_summary_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/inventory_valuation_summary_view.sql"
  content_type = "text/plain"
}

resource "google_cloud_run_v2_job" "etl_inventory_snapshot" {
  name     = "plex-etl-inventory-snapshot"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/reports/inventory_snapshot.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_inventory_snapshot" {
  name        = "plex-inventory-snapshot-sync"
  description = "Triggers Plex to BigQuery inventory snapshot ETL job"
  schedule    = "40 20 * * *" # 8:40 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_inventory_snapshot.name}:run"
    body        = base64encode("{}")
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

resource "google_cloud_scheduler_job" "etl_inventory_snapshot_retry" {
  name        = "plex-inventory-snapshot-sync-retry"
  description = "Retries the inventory snapshot ETL job if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_inventory_snapshot.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

resource "google_cloud_run_v2_job" "etl_inventory_snapshot_test" {
  name     = "plex-etl-inventory-snapshot-test"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset_test
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host_test
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/test/inventory_snapshot.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_inventory_snapshot_test" {
  name        = "plex-inventory-snapshot-sync-test"
  description = "Triggers Plex to BigQuery inventory snapshot ETL job (test)"
  schedule    = "50 20 * * *" # 8:50 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_inventory_snapshot_test.name}:run"
    body        = base64encode("{}")
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

resource "google_cloud_scheduler_job" "etl_inventory_snapshot_test_retry" {
  name        = "plex-inventory-snapshot-sync-test-retry"
  description = "Retries the inventory snapshot ETL job (test) if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_inventory_snapshot_test.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

# sales_orders_open_report SQL — new view added to the existing sales_orders
# report's bq_view list (reports/sales_orders.yaml). Requires the bq_view-list
# support in main.py, deployed 2026-08-11 — see block comment further up.
resource "google_storage_bucket_object" "sales_orders_open_view_sql" {
  name         = "sql/sales_orders_open_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_orders_open_view.sql"
  content_type = "text/plain"
}

# ═══════════════════════════════════════════════════════════════════════════
# MFG Job Schedule build (2026-08-11) — see docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md
# ═══════════════════════════════════════════════════════════════════════════

# mfg_job_schedule_report SQL + the updated work_orders.yaml configs (8 new
# extractions) — second bq_view on the EXISTING plex-etl-work-orders(-test)
# job. No new Cloud Run job/scheduler needed; work_orders_config_prod/test
# and work_orders_view_sql (defined earlier) already track these files by
# content hash and will re-upload them on apply.
resource "google_storage_bucket_object" "mfg_job_schedule_view_sql" {
  name         = "sql/mfg_job_schedule_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/mfg_job_schedule_view.sql"
  content_type = "text/plain"
}

# labeling_open_work_orders_report SQL — third bq_view on the same
# plex-etl-work-orders(-test) job, Plex-native rebuild of NetSuite's
# "Labeling | Open WO: Results". See reports-list/production.md.
resource "google_storage_bucket_object" "labeling_open_work_orders_view_sql" {
  name         = "sql/labeling_open_work_orders_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/labeling_open_work_orders_view.sql"
  content_type = "text/plain"
}

# ═══════════════════════════════════════════════════════════════════════════
# Catch-up batch (2026-08-19): 12 bq_view SQL files that were added to an
# EXISTING report's bq_view list (yaml already deployed) but never got a
# matching google_storage_bucket_object resource here — so `terraform apply`
# never actually uploaded them, and each one 404'd the first time its job
# tried to load it from GCS ("Failed to load view SQL ... 404 ... No such
# object"). Confirmed live 2026-08-19 against plex-etl-quality-nonconformance-test.
# Uploaded manually via `gcloud storage cp` to unblock the same night's runs;
# these resources make Terraform track them going forward like every other
# SQL file. No new Cloud Run job/scheduler needed for any of these — all 12
# ride on an existing job's periodic run.

# printing_open_work_orders_report — 4th bq_view on plex-etl-work-orders(-test).
resource "google_storage_bucket_object" "printing_open_work_orders_view_sql" {
  name         = "sql/printing_open_work_orders_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/printing_open_work_orders_view.sql"
  content_type = "text/plain"
}

# purchasing_po_pending_approval_report — 2nd bq_view on
# plex-etl-purchasing-open-orders(-test).
resource "google_storage_bucket_object" "purchasing_po_pending_approval_view_sql" {
  name         = "sql/purchasing_po_pending_approval_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/purchasing_po_pending_approval_view.sql"
  content_type = "text/plain"
}

# inventory_risk_analysis_report — 2nd bq_view on
# plex-etl-part-on-hand-inventory(-test).
resource "google_storage_bucket_object" "inventory_risk_analysis_view_sql" {
  name         = "sql/inventory_risk_analysis_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/inventory_risk_analysis_view.sql"
  content_type = "text/plain"
}

# quality_turnaround_time_report — 2nd bq_view on
# plex-etl-quality-nonconformance(-test), added 2026-08-14. This one had been
# broken since that date, not just introduced by today's catch-up.
resource "google_storage_bucket_object" "quality_turnaround_time_view_sql" {
  name         = "sql/quality_turnaround_time_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/quality_turnaround_time_view.sql"
  content_type = "text/plain"
}

# quality_deviation_report — 3rd bq_view on plex-etl-quality-nonconformance(-test),
# added 2026-08-19. See catalog/plex_quality_views_catalog.md "Deviations".
resource "google_storage_bucket_object" "quality_deviation_view_sql" {
  name         = "sql/quality_deviation_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/quality_deviation_view.sql"
  content_type = "text/plain"
}

# 6 additional bq_view entries on the existing plex-etl(-test) [sales_orders]
# job — NetSuite parity reports, see docs/NETSUITE_REPORT_BUILD_PLAN.md.
resource "google_storage_bucket_object" "sales_orders_pending_approval_view_sql" {
  name         = "sql/sales_orders_pending_approval_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_orders_pending_approval_view.sql"
  content_type = "text/plain"
}

# Added 2026-08-21 — "Orders Pending Approval by Sales Rep", a thin alias
# over sales_orders_pending_approval_view.sql (see that SQL file's header).
resource "google_storage_bucket_object" "sales_orders_pending_approval_by_rep_view_sql" {
  name         = "sql/sales_orders_pending_approval_by_rep_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_orders_pending_approval_by_rep_view.sql"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "sales_orders_pending_accounting_approval_view_sql" {
  name         = "sql/sales_orders_pending_accounting_approval_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_orders_pending_accounting_approval_view.sql"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "sales_orders_aging_view_sql" {
  name         = "sql/sales_orders_aging_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_orders_aging_view.sql"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "sales_orders_over_10k_view_sql" {
  name         = "sql/sales_orders_over_10k_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_orders_over_10k_view.sql"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "sales_orders_over_10k_bottles_view_sql" {
  name         = "sql/sales_orders_over_10k_bottles_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_orders_over_10k_bottles_view.sql"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "sales_customers_by_rep_view_sql" {
  name         = "sql/sales_customers_by_rep_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_customers_by_rep_view.sql"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "sales_revenue_by_rep_view_sql" {
  name         = "sql/sales_revenue_by_rep_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/sales_revenue_by_rep_view.sql"
  content_type = "text/plain"
}

# ── Quality Non-Conformance report — GCS config files ────────────────────────

resource "google_storage_bucket_object" "quality_nonconformance_config_prod" {
  name         = "reports/quality_nonconformance.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/quality_nonconformance.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "quality_nonconformance_config_test" {
  name         = "test/quality_nonconformance.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/test/quality_nonconformance.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "quality_nonconformance_view_sql" {
  name         = "sql/quality_nonconformance_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/quality_nonconformance_view.sql"
  content_type = "text/plain"
}

# ── Quality Non-Conformance — prod (PlexProd, 2 PM UTC) ───────────────────────

resource "google_cloud_run_v2_job" "etl_quality_nonconformance" {
  name     = "plex-etl-quality-nonconformance"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/reports/quality_nonconformance.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_quality_nonconformance" {
  name        = "plex-quality-nonconformance-sync"
  description = "Triggers Plex to BigQuery quality non-conformance ETL job"
  schedule    = "0 21 * * *" # 9:00 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_quality_nonconformance.name}:run"
    body        = base64encode("{}")
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

resource "google_cloud_scheduler_job" "etl_quality_nonconformance_retry" {
  name        = "plex-quality-nonconformance-sync-retry"
  description = "Retries the quality non-conformance ETL job if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_quality_nonconformance.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

# ── Quality Non-Conformance — test (PlexTest, 3 PM UTC) ───────────────────────

resource "google_cloud_run_v2_job" "etl_quality_nonconformance_test" {
  name     = "plex-etl-quality-nonconformance-test"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset_test
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host_test
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/test/quality_nonconformance.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_quality_nonconformance_test" {
  name        = "plex-quality-nonconformance-sync-test"
  description = "Triggers Plex to BigQuery quality non-conformance ETL job (test)"
  schedule    = "10 21 * * *" # 9:10 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_quality_nonconformance_test.name}:run"
    body        = base64encode("{}")
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

resource "google_cloud_scheduler_job" "etl_quality_nonconformance_test_retry" {
  name        = "plex-quality-nonconformance-sync-test-retry"
  description = "Retries the quality non-conformance ETL job (test) if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_quality_nonconformance_test.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

# ── Part On-Hand Inventory report — GCS config files ──────────────────────────

resource "google_storage_bucket_object" "part_on_hand_inventory_config_prod" {
  name         = "reports/part_on_hand_inventory.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/part_on_hand_inventory.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "part_on_hand_inventory_config_test" {
  name         = "test/part_on_hand_inventory.yaml"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/test/part_on_hand_inventory.yaml"
  content_type = "text/plain"
}

resource "google_storage_bucket_object" "part_on_hand_inventory_view_sql" {
  name         = "sql/part_on_hand_inventory_view.sql"
  bucket       = google_storage_bucket.report_configs.name
  source       = "${path.module}/../reports/sql/part_on_hand_inventory_view.sql"
  content_type = "text/plain"
}

# ── Part On-Hand Inventory — prod (PlexProd, 4 PM UTC) ────────────────────────

resource "google_cloud_run_v2_job" "etl_part_on_hand_inventory" {
  name     = "plex-etl-part-on-hand-inventory"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/reports/part_on_hand_inventory.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_part_on_hand_inventory" {
  name        = "plex-part-on-hand-inventory-sync"
  description = "Triggers Plex to BigQuery part on-hand inventory ETL job"
  schedule    = "20 21 * * *" # 9:20 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_part_on_hand_inventory.name}:run"
    body        = base64encode("{}")
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

resource "google_cloud_scheduler_job" "etl_part_on_hand_inventory_retry" {
  name        = "plex-part-on-hand-inventory-sync-retry"
  description = "Retries the part on-hand inventory ETL job if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_part_on_hand_inventory.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

# ── Part On-Hand Inventory — test (PlexTest, 5 PM UTC) ────────────────────────

resource "google_cloud_run_v2_job" "etl_part_on_hand_inventory_test" {
  name     = "plex-etl-part-on-hand-inventory-test"
  location = var.gcp_region

  template {
    template {
      service_account = google_service_account.etl.email
      containers {
        image = var.image_url
        env {
          name  = "GCP_PROJECT"
          value = var.gcp_project
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset_test
        }
        env {
          name  = "BQ_TABLE"
          value = var.bq_table
        }
        env {
          name  = "PLEX_HOST"
          value = var.plex_host_test
        }
        env {
          name  = "PLEX_PORT"
          value = "19995"
        }
        env {
          name  = "PLEX_SERVER_DATASOURCE"
          value = "ReportDataSource"
        }
        env {
          name  = "PLEX_ODBC_USER"
          value = var.plex_odbc_user
        }
        env {
          name  = "SECRET_ACCESS_TOKEN"
          value = var.secret_access_token
        }
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
        }
        env {
          name  = "SECRET_ODBC_USER"
          value = var.secret_odbc_user
        }
        env {
          name  = "SECRET_ODBC_PASSWORD"
          value = var.secret_odbc_password
        }
        env {
          name  = "SECRET_COMPANY_CODE"
          value = var.secret_company_code
        }
        env {
          name  = "REPORT_CONFIG_GCS_PATH"
          value = "gs://${var.report_configs_bucket}/test/part_on_hand_inventory.yaml"
        }
        env {
          name  = "PLEX_VIEW"
          value = var.plex_view
        }
        env {
          name  = "PLEX_FILTER"
          value = var.plex_filter
        }
        env {
          name  = "PLEX_DATE_COL"
          value = var.plex_date_col
        }
        env {
          name  = "METADATA_TABLE"
          value = var.metadata_table
        }
        env {
          name  = "BACKFILL_MINUTES"
          value = tostring(var.backfill_minutes)
        }
        env {
          name  = "SENDGRID_ENABLED"
          value = var.sendgrid_enabled
        }
        env {
          name  = "REPORT_FROM_EMAIL"
          value = var.report_from_email
        }
        env {
          name  = "REPORT_TO_EMAILS"
          value = var.report_to_emails
        }
        env {
          name  = "REPORT_SUBJECT"
          value = var.report_subject
        }
        env {
          name  = "SECRET_SENDGRID_KEY"
          value = var.secret_sendgrid_key
        }
        env {
          name  = "COMPANY_NAME"
          value = var.company_name
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }

  # Image is deliberately NOT managed by Terraform — deploy/cloudbuild.yaml
  # (or a manual `gcloud run jobs update --image=...`) owns the deployed
  # image tag for every plex-etl-* job. Terraform still declares an initial
  # pinned SHA in var.image_url for first-time creation, but ignores drift
  # on this field afterward — the standard split for "IaC owns resource
  # shape, CI/CD owns application version" (see HashiCorp's ignore_changes
  # docs). This is what stops a routine `terraform apply` from silently
  # reverting a job to a stale/different image.
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_scheduler_job" "etl_part_on_hand_inventory_test" {
  name        = "plex-part-on-hand-inventory-sync-test"
  description = "Triggers Plex to BigQuery part on-hand inventory ETL job (test)"
  schedule    = "30 21 * * *" # 9:30 PM Mountain — see scheduler_time_zone
  time_zone   = var.scheduler_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_part_on_hand_inventory_test.name}:run"
    body        = base64encode("{}")
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}

resource "google_cloud_scheduler_job" "etl_part_on_hand_inventory_test_retry" {
  name        = "plex-part-on-hand-inventory-sync-test-retry"
  description = "Retries the part on-hand inventory ETL job (test) if today's scheduled run failed"
  schedule    = var.retry_scheduler_cron
  time_zone   = var.retry_time_zone
  region      = var.gcp_region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.gcp_project}/locations/${var.gcp_region}/jobs/${google_cloud_run_v2_job.etl_part_on_hand_inventory_test.name}:run"
    body = base64encode(jsonencode({
      overrides = {
        containerOverrides = [{
          env = [{ name = "RUN_MODE", value = "retry" }]
        }]
      }
    }))
    oauth_token { service_account_email = google_service_account.etl.email }
  }
}
