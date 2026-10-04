import html
import json
import logging
import os
import random
import re
from typing import List, Optional
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


@functions_framework.http
def send_vocab_task(request):
    logger.info("Function triggered by Cloud Scheduler.")

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
        return (error_msg, 500)

    with httpx.Client(timeout=60.0) as client:
        # 1. Fetch pinned message from Telegram Channel
        chat_url = f"https://api.telegram.org/bot{telegram_bot_token}/getChat"
        try:
            chat_resp = client.post(chat_url, json={"chat_id": telegram_chat_id})
        except Exception as e:
            logger.error("Failed to connect to Telegram getChat: %s", e)
            return ("Error connecting to Telegram", 500)

        if chat_resp.status_code != 200:
            logger.error("Failed to get chat info (%s): %s", chat_resp.status_code, chat_resp.text)
            return ("Error fetching Telegram chat", 500)

        chat_data = chat_resp.json()
        pinned = chat_data.get("result", {}).get("pinned_message", {})
        raw_text = pinned.get("text") or pinned.get("caption") or ""

        if not raw_text:
            logger.warning("No text found in pinned message.")
            return ("Pinned message empty", 200)

        all_words = extract_words_from_pinned(raw_text)
        if not all_words:
            logger.warning("Could not extract any words.")
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
            return ("OpenAI connection error", 500)

        if openai_resp.status_code != 200:
            logger.error("OpenAI API error (%s): %s", openai_resp.status_code, openai_resp.text)
            return ("OpenAI API error", 500)

        try:
            res_json = openai_resp.json()
            raw_content = res_json["choices"][0]["message"]["content"]
            batch = VocabBatch.model_validate_json(raw_content)
        except Exception as e:
            logger.error("Failed to parse OpenAI response: %s", e)
            return ("Invalid OpenAI response format", 500)

        # 3. ElevenLabs TTS & Telegram Delivery
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
                    else:
                        logger.warning(
                            "TTS failed with status %s: %s. Falling back to text-only.",
                            tts_resp.status_code,
                            tts_resp.text,
                        )
                except Exception as e:
                    logger.warning("TTS request exception: %s. Falling back to text-only.", e)
            else:
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
                        logger.error("Telegram sendVoice failed (%s): %s", v_resp.status_code, v_resp.text)
                except Exception as e:
                    logger.error("Failed to send voice message to Telegram: %s", e)
            else:
                send_msg_url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
                try:
                    m_resp = client.post(
                        send_msg_url,
                        json={"chat_id": telegram_chat_id, "text": caption, "parse_mode": "HTML"},
                    )
                    if m_resp.status_code != 200:
                        logger.error("Telegram sendMessage failed (%s): %s", m_resp.status_code, m_resp.text)
                except Exception as e:
                    logger.error("Failed to send text message to Telegram: %s", e)

    return ("Batch processed and sent successfully", 200)
