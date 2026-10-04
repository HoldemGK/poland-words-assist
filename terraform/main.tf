# Polish Vocab Bot Infrastructure (Cloud Run Function, Secret Manager, Cloud Scheduler)

# --- Service APIs ---
resource "google_project_service" "enabled_apis" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}

# --- Service Account for Invoker & Runtime ---
resource "google_service_account" "bot_sa" {
  account_id   = "polish-vocab-bot-sa"
  display_name = "Polish Vocab Bot Cloud Run Service Account"
  depends_on   = [google_project_service.enabled_apis]
}

resource "google_service_account" "scheduler_sa" {
  account_id   = "polish-vocab-scheduler-sa"
  display_name = "Cloud Scheduler Invoker SA"
  depends_on   = [google_project_service.enabled_apis]
}

# --- Secret Manager ---
resource "google_secret_manager_secret" "telegram_token" {
  secret_id = "TELEGRAM_BOT_TOKEN"
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled_apis]
}

resource "google_secret_manager_secret_version" "telegram_token_val" {
  secret      = google_secret_manager_secret.telegram_token.id
  secret_data = var.telegram_bot_token
}

resource "google_secret_manager_secret" "openai_key" {
  secret_id = "OPENAI_API_KEY"
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled_apis]
}

resource "google_secret_manager_secret_version" "openai_key_val" {
  secret      = google_secret_manager_secret.openai_key.id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret" "elevenlabs_key" {
  secret_id = "ELEVENLABS_API_KEY"
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled_apis]
}

resource "google_secret_manager_secret_version" "elevenlabs_key_val" {
  secret      = google_secret_manager_secret.elevenlabs_key.id
  secret_data = var.elevenlabs_api_key
}

# Grant SA access to read secrets
resource "google_secret_manager_secret_iam_member" "secret_access" {
  for_each = {
    telegram   = google_secret_manager_secret.telegram_token.secret_id
    openai     = google_secret_manager_secret.openai_key.secret_id
    elevenlabs = google_secret_manager_secret.elevenlabs_key.secret_id
  }
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.bot_sa.email}"
}

# --- Function Source Code Packaging ---
data "archive_file" "function_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/function-source.zip"
}

resource "google_storage_bucket" "source_bucket" {
  name                        = "${var.project_id}-vocab-bot-source"
  location                    = var.region
  uniform_bucket_level_access = true
  depends_on                  = [google_project_service.enabled_apis]
}

resource "google_storage_bucket_object" "source_zip" {
  name   = "source-${data.archive_file.function_zip.output_md5}.zip"
  bucket = google_storage_bucket.source_bucket.name
  source = data.archive_file.function_zip.output_path
}

# --- Cloud Run Function (2nd Gen) ---
resource "google_cloudfunctions2_function" "vocab_function" {
  name        = "polish-vocab-generator"
  location    = var.region
  description = "Generates Polish sentences and synthesizes audio into Telegram"

  build_config {
    runtime     = "python311"
    entry_point = "send_vocab_task"
    source {
      storage_source {
        bucket = google_storage_bucket.source_bucket.name
        object = google_storage_bucket_object.source_zip.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    min_instance_count    = 0
    available_memory      = "512M"
    timeout_seconds       = 120
    service_account_email = google_service_account.bot_sa.email

    environment_variables = {
      TELEGRAM_CHAT_ID    = var.telegram_chat_id
      ELEVENLABS_VOICE_ID = var.elevenlabs_voice_id
    }

    secret_environment_variables {
      key        = "TELEGRAM_BOT_TOKEN"
      project_id = var.project_id
      secret     = google_secret_manager_secret.telegram_token.secret_id
      version    = "latest"
    }
    secret_environment_variables {
      key        = "OPENAI_API_KEY"
      project_id = var.project_id
      secret     = google_secret_manager_secret.openai_key.secret_id
      version    = "latest"
    }
    secret_environment_variables {
      key        = "ELEVENLABS_API_KEY"
      project_id = var.project_id
      secret     = google_secret_manager_secret.elevenlabs_key.secret_id
      version    = "latest"
    }
  }

  depends_on = [
    google_project_service.enabled_apis,
    google_secret_manager_secret_iam_member.secret_access
  ]
}

# Allow Scheduler SA to invoke Function
resource "google_cloud_run_service_iam_member" "invoker_role" {
  location = google_cloudfunctions2_function.vocab_function.location
  service  = google_cloudfunctions2_function.vocab_function.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_sa.email}"
}

# --- Cloud Scheduler (Every 3 hours during day) ---
resource "google_cloud_scheduler_job" "cron_trigger" {
  name             = "polish-vocab-3h-cron"
  description      = "Trigger Polish vocab generation every 3 hours (9:00 - 21:00)"
  schedule         = "0 9,12,15,18,21 * * *"
  time_zone        = var.time_zone
  attempt_deadline = "180s"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.vocab_function.service_config[0].uri

    oidc_token {
      service_account_email = google_service_account.scheduler_sa.email
      audience              = google_cloudfunctions2_function.vocab_function.service_config[0].uri
    }
  }

  depends_on = [
    google_project_service.enabled_apis,
    google_cloud_run_service_iam_member.invoker_role
  ]
}
