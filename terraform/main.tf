terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
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
  dataset_id = google_bigquery_dataset.plex.dataset_id
  table_id   = var.metadata_table

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
  secret_id  = var.secret_odbc_user
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "odbc_password" {
  secret_id  = var.secret_odbc_password
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "company_code" {
  secret_id  = var.secret_company_code
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
        # Plex query config — which view and filter to run
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
      max_retries = 3
      timeout     = "600s"
    }
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
