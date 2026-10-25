-- ==============================================================================
-- Polish Vocab Bot: Unified Consumption View for Looker Studio
-- ==============================================================================
-- Dataset: vocab_bot_telemetry
-- View Name: v_consumption_metrics
-- Description: Flattens structured JSON telemetry from Cloud Run stdout into 
--              clean, type-safe analytical columns for Looker Studio dashboards.
-- ==============================================================================

CREATE OR REPLACE VIEW `vocab_bot_telemetry.v_consumption_metrics` AS
SELECT
  timestamp AS execution_timestamp,
  DATE(timestamp, "Europe/Warsaw") AS execution_date,
  TIME(timestamp, "Europe/Warsaw") AS execution_time,
  jsonPayload.run_id AS run_id,
  jsonPayload.status AS status,
  
  -- OpenAI Metrics
  jsonPayload.openai.model AS openai_model,
  COALESCE(jsonPayload.openai.prompt_tokens, 0) AS openai_prompt_tokens,
  COALESCE(jsonPayload.openai.completion_tokens, 0) AS openai_completion_tokens,
  COALESCE(jsonPayload.openai.total_tokens, 0) AS openai_total_tokens,
  COALESCE(jsonPayload.openai.cost_usd, 0.0) AS openai_cost_usd,

  -- ElevenLabs TTS Metrics
  jsonPayload.elevenlabs.voice_id AS elevenlabs_voice_id,
  COALESCE(jsonPayload.elevenlabs.characters_used, 0) AS elevenlabs_chars_used,
  COALESCE(jsonPayload.elevenlabs.audio_bytes, 0) AS elevenlabs_audio_bytes,
  COALESCE(jsonPayload.elevenlabs.fallback_count, 0) AS elevenlabs_fallback_count,
  jsonPayload.elevenlabs.account_character_count AS elevenlabs_account_character_count,
  jsonPayload.elevenlabs.account_character_limit AS elevenlabs_account_character_limit,
  jsonPayload.elevenlabs.account_percent_used AS elevenlabs_account_percent_used,

  -- Telegram Metrics
  COALESCE(jsonPayload.telegram.voices_sent, 0) AS telegram_voices_sent,
  COALESCE(jsonPayload.telegram.texts_sent, 0) AS telegram_texts_sent,
  COALESCE(jsonPayload.telegram.total_audio_bytes, 0) AS telegram_total_audio_bytes,
  COALESCE(jsonPayload.telegram.errors, 0) AS telegram_errors,

  -- Google Cloud Metrics
  COALESCE(jsonPayload.gcp.duration_ms, 0.0) AS gcp_duration_ms,
  COALESCE(jsonPayload.gcp.memory_mb, 512) AS gcp_memory_mb,

  -- Success Indicator
  CASE 
    WHEN jsonPayload.status = 'success' THEN 1 
    ELSE 0 
  END AS is_success
FROM
  `vocab_bot_telemetry.run_googleapis_com_stdout`
WHERE
  jsonPayload.telemetry_type = 'service_consumption'
ORDER BY
  timestamp DESC;
