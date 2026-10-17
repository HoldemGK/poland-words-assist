output "function_uri" {
  value       = google_cloudfunctions2_function.vocab_function.service_config[0].uri
  description = "HTTPS trigger URL of the Cloud Run Function"
}

output "scheduler_job_name" {
  value       = google_cloud_scheduler_job.cron_trigger.name
  description = "Name of the Cloud Scheduler job"
}

output "bigquery_dataset_id" {
  value       = google_bigquery_dataset.telemetry.dataset_id
  description = "BigQuery dataset ID storing consumption telemetry"
}

output "bigquery_log_sink_name" {
  value       = google_logging_project_sink.consumption_sink.name
  description = "Name of Cloud Logging Log Router sink"
}

output "bigquery_log_sink_writer" {
  value       = google_logging_project_sink.consumption_sink.writer_identity
  description = "Service Account identity writing logs to BigQuery"
}
