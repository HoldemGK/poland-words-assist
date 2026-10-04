variable "project_id" {
  type        = string
  description = "Google Cloud Project ID"
}

variable "region" {
  type        = string
  default     = "europe-west1"
  description = "GCP Region for Cloud Run Functions"
}

variable "time_zone" {
  type        = string
  default     = "Europe/Warsaw"
  description = "Time zone for Cloud Scheduler cron"
}

variable "telegram_bot_token" {
  type        = string
  sensitive   = true
  description = "Telegram Bot Token from @BotFather"
}

variable "telegram_chat_id" {
  type        = string
  description = "Telegram channel @username or numerical ID"
}

variable "openai_api_key" {
  type        = string
  sensitive   = true
  description = "OpenAI API Key"
}

variable "elevenlabs_api_key" {
  type        = string
  sensitive   = true
  description = "ElevenLabs API Key"
}

variable "elevenlabs_voice_id" {
  type        = string
  default     = "pNInz6obpgDQGcFmaJgB" # Adam (Multilingual) or custom Polish voice
  description = "Voice ID for Polish TTS"
}
