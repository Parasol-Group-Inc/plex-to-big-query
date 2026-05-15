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

resource "google_bigquery_dataset" "plex" {
  dataset_id                 = var.bq_dataset
  location                   = var.bq_location
  delete_contents_on_destroy = false
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
        env {
          name  = "PLEX_DSN"
          value = var.plex_dsn
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
    uri         = "https://${var.gcp_region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.gcp_project}/jobs/${google_cloud_run_v2_job.etl.name}:run"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.etl.email
    }
  }
}
