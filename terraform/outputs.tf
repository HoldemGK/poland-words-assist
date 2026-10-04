output "function_uri" {
  value       = google_cloudfunctions2_function.vocab_function.service_config[0].uri
  description = "HTTPS trigger URL of the Cloud Run Function"
}

output "scheduler_job_name" {
  value       = google_cloud_scheduler_job.cron_trigger.name
  description = "Name of the Cloud Scheduler job"
}
