import datetime
import html
import json
import logging
import os
import random
import re
import time
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import functions_framework
import httpx
from pydantic import BaseModel, ConfigDict, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config defaults / helpers
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"


class VocabItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: str
    pl_sentence: str = Field(description="Natural A2/B1 CEFR Polish sentence using the word")
    ru_translation: str = Field(description="Russian translation of the sentence")


class VocabBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[VocabItem]


def extract_words_from_pinned(raw_text: str) -> List[str]:
    """
    Parses pinned message text, removing bullet points, numbering, and translations,
    and returns a unique list of candidate Polish words.
    """
    lines = raw_text.splitlines()
    words = []
    for line in lines:
        cleaned = re.sub(r"^[\s*•\-\d\.\)]+", "", line).strip()
        cleaned = re.split(r"[–—\-:]", cleaned)[0].strip()
        if cleaned and len(cleaned) < 35:
            words.append(cleaned)
    # Deduplicate while preserving order
    return list(dict.fromkeys(words))


def emit_telemetry(
    run_id: str,
    start_time: float,
    status: str,
    openai_metrics: Optional[dict] = None,
    elevenlabs_metrics: Optional[dict] = None,
    telegram_metrics: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> None:
    """Emits structured JSON telemetry to stdout for Google Cloud Logging and BigQuery ingestion."""
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    payload = {
        "telemetry_type": "service_consumption",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "status": status,
        "openai": openai_metrics or {
            "model": "gpt-4o-mini",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
        },
        "elevenlabs": elevenlabs_metrics or {
            "voice_id": "",
            "characters_used": 0,
            "audio_bytes": 0,
            "fallback_count": 0,
            "account_character_count": None,
            "account_character_limit": None,
            "account_percent_used": None,
        },
        "telegram": telegram_metrics or {
            "voices_sent": 0,
            "texts_sent": 0,
            "total_audio_bytes": 0,
            "errors": 0,
        },
        "gcp": {
            "duration_ms": duration_ms,
            "memory_mb": 512,
        },
    }
    if extra:
        payload["extra"] = extra
    logger.info(json.dumps(payload))


@functions_framework.http
def send_vocab_task(request):
    start_time = time.perf_counter()
    run_id = uuid.uuid4().hex[:8]
    logger.info("Function triggered by Cloud Scheduler. Run ID: %s", run_id)

    # Read configuration dynamically from environment (supports standard runtime and TF_VAR_* from .env)
    telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TF_VAR_telegram_bot_token")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TF_VAR_telegram_chat_id")
    openai_api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TF_VAR_openai_api_key")
    elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("TF_VAR_elevenlabs_api_key")
    elevenlabs_voice_id = (
        os.environ.get("ELEVENLABS_VOICE_ID")
        or os.environ.get("TF_VAR_elevenlabs_voice_id")
        or DEFAULT_VOICE_ID
    )

    # Validate essential environment variables
    missing_vars = []
    if not telegram_bot_token:
        missing_vars.append("TELEGRAM_BOT_TOKEN / TF_VAR_telegram_bot_token")
    if not telegram_chat_id:
        missing_vars.append("TELEGRAM_CHAT_ID / TF_VAR_telegram_chat_id")
    if not openai_api_key:
        missing_vars.append("OPENAI_API_KEY / TF_VAR_openai_api_key")
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        emit_telemetry(run_id, start_time, status="error_missing_env", extra={"error": error_msg})
        return (error_msg, 500)

    with httpx.Client(timeout=60.0) as client:
        # 1. Fetch pinned message from Telegram Channel
        chat_url = f"https://api.telegram.org/bot{telegram_bot_token}/getChat"
        try:
            chat_resp = client.post(chat_url, json={"chat_id": telegram_chat_id})
        except Exception as e:
            logger.error("Failed to connect to Telegram getChat: %s", e)
            emit_telemetry(run_id, start_time, status="error_telegram_connection", extra={"error": str(e)})
            return ("Error connecting to Telegram", 500)

        if chat_resp.status_code != 200:
            logger.error("Failed to get chat info (%s): %s", chat_resp.status_code, chat_resp.text)
            emit_telemetry(run_id, start_time, status="error_telegram_chat_fetch", extra={"status_code": chat_resp.status_code})
            return ("Error fetching Telegram chat", 500)

        chat_data = chat_resp.json()
        pinned = chat_data.get("result", {}).get("pinned_message", {})
        raw_text = pinned.get("text") or pinned.get("caption") or ""

        if not raw_text:
            logger.warning("No text found in pinned message.")
            emit_telemetry(run_id, start_time, status="skipped_empty_pinned")
            return ("Pinned message empty", 200)

        all_words = extract_words_from_pinned(raw_text)
        if not all_words:
            logger.warning("Could not extract any words.")
            emit_telemetry(run_id, start_time, status="skipped_no_words")
            return ("No words extracted", 200)

        sample_size = min(3, max(1, len(all_words)))
        selected_words = random.sample(all_words, sample_size)
        logger.info("Selected words for drilling: %s", selected_words)

        # 2. Generate sentences via OpenAI (Structured Outputs)
        prompt = (
            f"Generate CEFR A2/B1 level Polish example sentences and Russian translations "
            f"for these words: {', '.join(selected_words)}."
        )

        try:
            openai_resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {openai_api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are an expert Polish language tutor. Create engaging, "
                                "practical CEFR A2/B1 example sentences for given Polish words. "
                                "Provide accurate Russian translations."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "vocab_batch",
                            "strict": True,
                            "schema": VocabBatch.model_json_schema(),
                        },
                    },
                },
            )
        except Exception as e:
            logger.error("OpenAI request connection error: %s", e)
            emit_telemetry(run_id, start_time, status="error_openai_connection", extra={"error": str(e)})
            return ("OpenAI connection error", 500)

        if openai_resp.status_code != 200:
            logger.error("OpenAI API error (%s): %s", openai_resp.status_code, openai_resp.text)
            emit_telemetry(run_id, start_time, status="error_openai_api", extra={"status_code": openai_resp.status_code})
            return ("OpenAI API error", 500)

        openai_metrics = {
            "model": "gpt-4o-mini",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
        }

        try:
            res_json = openai_resp.json()
            usage_info = res_json.get("usage", {})
            prompt_tokens = usage_info.get("prompt_tokens", 0)
            completion_tokens = usage_info.get("completion_tokens", 0)
            total_tokens = usage_info.get("total_tokens", prompt_tokens + completion_tokens)
            # gpt-4o-mini pricing: $0.150 per 1M input tokens, $0.600 per 1M output tokens
            cost_usd = (prompt_tokens * 0.150 / 1_000_000) + (completion_tokens * 0.600 / 1_000_000)
            openai_metrics = {
                "model": "gpt-4o-mini",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": round(cost_usd, 6),
            }

            raw_content = res_json["choices"][0]["message"]["content"]
            batch = VocabBatch.model_validate_json(raw_content)
        except Exception as e:
            logger.error("Failed to parse OpenAI response: %s", e)
            emit_telemetry(run_id, start_time, status="error_openai_parse", openai_metrics=openai_metrics, extra={"error": str(e)})
            return ("Invalid OpenAI response format", 500)

        # 3. ElevenLabs TTS & Telegram Delivery
        total_chars_synthesized = 0
        total_audio_bytes = 0
        voices_sent = 0
        texts_sent = 0
        tts_fallbacks = 0
        tg_errors = 0

        for item in batch.items:
            safe_word = html.escape(item.word, quote=False)
            safe_pl = html.escape(item.pl_sentence, quote=False)
            safe_ru = html.escape(item.ru_translation, quote=False)

            caption = (
                f"🇵🇱 <b>{safe_word}</b>\n"
                f"🗣️ {safe_pl}\n"
                f"🇷🇺 <tg-spoiler>{safe_ru}</tg-spoiler>"
            )

            # Synthesize audio (Voice ONLY the Polish sentence)
            audio_bytes: Optional[bytes] = None
            if elevenlabs_api_key:
                tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{elevenlabs_voice_id}"
                try:
                    tts_resp = client.post(
                        tts_url,
                        headers={"xi-api-key": elevenlabs_api_key},
                        json={
                            "text": item.pl_sentence,
                            "model_id": "eleven_multilingual_v2",
                            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
                        },
                    )
                    if tts_resp.status_code == 200:
                        audio_bytes = tts_resp.content
                        total_chars_synthesized += len(item.pl_sentence)
                        total_audio_bytes += len(audio_bytes)
                    else:
                        tts_fallbacks += 1
                        logger.warning(
                            "TTS failed with status %s: %s. Falling back to text-only.",
                            tts_resp.status_code,
                            tts_resp.text,
                        )
                except Exception as e:
                    tts_fallbacks += 1
                    logger.warning("TTS request exception: %s. Falling back to text-only.", e)
            else:
                tts_fallbacks += 1
                logger.info("ELEVENLABS_API_KEY not configured, using text-only delivery.")

            # Deliver to Telegram: voice note or text fallback
            if audio_bytes:
                send_voice_url = f"https://api.telegram.org/bot{telegram_bot_token}/sendVoice"
                try:
                    v_resp = client.post(
                        send_voice_url,
                        data={"chat_id": telegram_chat_id, "caption": caption, "parse_mode": "HTML"},
                        files={"voice": ("sentence.mp3", audio_bytes, "audio/mpeg")},
                    )
                    if v_resp.status_code != 200:
                        tg_errors += 1
                        logger.error("Telegram sendVoice failed (%s): %s", v_resp.status_code, v_resp.text)
                    else:
                        voices_sent += 1
                except Exception as e:
                    tg_errors += 1
                    logger.error("Failed to send voice message to Telegram: %s", e)
            else:
                send_msg_url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
                try:
                    m_resp = client.post(
                        send_msg_url,
                        json={"chat_id": telegram_chat_id, "text": caption, "parse_mode": "HTML"},
                    )
                    if m_resp.status_code != 200:
                        tg_errors += 1
                        logger.error("Telegram sendMessage failed (%s): %s", m_resp.status_code, m_resp.text)
                    else:
                        texts_sent += 1
                except Exception as e:
                    tg_errors += 1
                    logger.error("Failed to send text message to Telegram: %s", e)

        # Inspect account subscription balance if ElevenLabs was called
        account_chars = None
        account_limit = None
        account_percent = None
        if elevenlabs_api_key and total_chars_synthesized > 0:
            try:
                sub_url = "https://api.elevenlabs.io/v1/user/subscription"
                sub_resp = client.get(sub_url, headers={"xi-api-key": elevenlabs_api_key}, timeout=5.0)
                if sub_resp.status_code == 200:
                    sub_data = sub_resp.json()
                    account_chars = sub_data.get("character_count")
                    account_limit = sub_data.get("character_limit")
                    if account_chars is not None and account_limit and account_limit > 0:
                        account_percent = round((account_chars / account_limit) * 100, 2)
            except Exception as e:
                logger.debug("Optional ElevenLabs subscription balance check skipped: %s", e)

        elevenlabs_metrics = {
            "voice_id": elevenlabs_voice_id,
            "characters_used": total_chars_synthesized,
            "audio_bytes": total_audio_bytes,
            "fallback_count": tts_fallbacks,
            "account_character_count": account_chars,
            "account_character_limit": account_limit,
            "account_percent_used": account_percent,
        }

        telegram_metrics = {
            "voices_sent": voices_sent,
            "texts_sent": texts_sent,
            "total_audio_bytes": total_audio_bytes,
            "errors": tg_errors,
        }

        emit_telemetry(
            run_id=run_id,
            start_time=start_time,
            status="success",
            openai_metrics=openai_metrics,
            elevenlabs_metrics=elevenlabs_metrics,
            telegram_metrics=telegram_metrics,
            extra={"selected_words_count": len(selected_words)},
        )

    return ("Batch processed and sent successfully", 200)
