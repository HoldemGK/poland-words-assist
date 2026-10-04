import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from main import VocabItem, VocabBatch, extract_words_from_pinned, send_vocab_task


class TestVocabExtraction(unittest.TestCase):
    def test_extract_words_various_formats(self):
        sample_text = """
        Lista słówek:
        1. cześć - привет
        2. dziękuję — спасибо
        3. proszę – пожалуйста
        • samochód: машина
        - pociąg - поезд
        * samolot - самолет
        ) jabłko
        
        To jest zbyt długie zdanie które nie powinno zostać uznane za pojedyncze słowo bo przekracza 35 znaków
        """
        words = extract_words_from_pinned(sample_text)
        self.assertIn("cześć", words)
        self.assertIn("dziękuję", words)
        self.assertIn("proszę", words)
        self.assertIn("samochód", words)
        self.assertIn("pociąg", words)
        self.assertIn("samolot", words)
        self.assertIn("jabłko", words)
        self.assertNotIn("To jest zbyt długie zdanie które nie powinno zostać uznane za pojedyncze słowo bo przekracza 35 znaków", words)

    def test_extract_words_deduplication(self):
        sample_text = """
        1. kawa - кофе
        2. herbata - чай
        3. kawa - кофе
        """
        words = extract_words_from_pinned(sample_text)
        self.assertEqual(words.count("kawa"), 1)
        self.assertEqual(words, ["kawa", "herbata"])

    def test_extract_words_empty(self):
        self.assertEqual(extract_words_from_pinned(""), [])
        self.assertEqual(extract_words_from_pinned("   \n\n  "), [])


class TestVocabBatchSchema(unittest.TestCase):
    def test_schema_extra_forbid(self):
        schema = VocabBatch.model_json_schema()
        self.assertFalse(schema.get("additionalProperties", True))
        self.assertIn("items", schema.get("required", []))
        item_schema = schema["$defs"]["VocabItem"]
        self.assertFalse(item_schema.get("additionalProperties", True))
        self.assertEqual(set(item_schema.get("required", [])), {"word", "pl_sentence", "ru_translation"})

    def test_model_validation(self):
        valid_json = """
        {
            "items": [
                {
                    "word": "pies",
                    "pl_sentence": "Mój pies lubi biegać w parku.",
                    "ru_translation": "Моя собака любит бегать в парке."
                }
            ]
        }
        """
        batch = VocabBatch.model_validate_json(valid_json)
        self.assertEqual(len(batch.items), 1)
        self.assertEqual(batch.items[0].word, "pies")


class TestSendVocabTaskHandler(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_env_vars(self):
        response, status = send_vocab_task(MagicMock())
        self.assertEqual(status, 500)
        self.assertIn("Missing required environment variables", response)

    @patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "mock_token",
        "TELEGRAM_CHAT_ID": "@mock_channel",
        "OPENAI_API_KEY": "mock_openai",
        "ELEVENLABS_API_KEY": "mock_eleven",
    })
    @patch("main.httpx.Client")
    def test_full_successful_flow(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        # Mock Telegram getChat
        mock_chat_resp = MagicMock(status_code=200)
        mock_chat_resp.json.return_value = {
            "result": {
                "pinned_message": {
                    "text": "1. szkoła - школа\n2. dom - дом"
                }
            }
        }

        # Mock OpenAI chat completions
        mock_openai_resp = MagicMock(status_code=200)
        mock_openai_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"items": [{"word": "szkoła", "pl_sentence": "Idę do szkoły.", "ru_translation": "Я иду в школу."}]}'
                    }
                }
            ]
        }

        # Mock ElevenLabs TTS
        mock_tts_resp = MagicMock(status_code=200, content=b"fake_mp3_data")

        # Mock Telegram sendVoice
        mock_send_voice_resp = MagicMock(status_code=200)

        mock_client.post.side_effect = [
            mock_chat_resp,
            mock_openai_resp,
            mock_tts_resp,
            mock_send_voice_resp,
        ]

        response, status = send_vocab_task(MagicMock())
        self.assertEqual(status, 200)
        self.assertEqual(response, "Batch processed and sent successfully")
        self.assertEqual(mock_client.post.call_count, 4)

    @patch.dict(os.environ, {
        "TF_VAR_telegram_bot_token": "mock_token_tf",
        "TF_VAR_telegram_chat_id": "@mock_channel_tf",
        "TF_VAR_openai_api_key": "mock_openai_tf",
        "TF_VAR_elevenlabs_api_key": "mock_eleven_tf",
        "TF_VAR_elevenlabs_voice_id": "mock_voice_tf",
    }, clear=True)
    @patch("main.httpx.Client")
    def test_tf_var_env_vars_support(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_chat_resp = MagicMock(status_code=200)
        mock_chat_resp.json.return_value = {
            "result": {"pinned_message": {"text": "1. herbata - чай"}}
        }
        mock_openai_resp = MagicMock(status_code=200)
        mock_openai_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"items": [{"word": "herbata", "pl_sentence": "Piję herbatę.", "ru_translation": "Я пью чай."}]}'
                }
            }]
        }
        mock_tts_resp = MagicMock(status_code=200, content=b"audio_bytes")
        mock_send_voice_resp = MagicMock(status_code=200)

        mock_client.post.side_effect = [
            mock_chat_resp,
            mock_openai_resp,
            mock_tts_resp,
            mock_send_voice_resp,
        ]

        response, status = send_vocab_task(MagicMock())
        self.assertEqual(status, 200)
        self.assertEqual(response, "Batch processed and sent successfully")

    @patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "mock_token",
        "TELEGRAM_CHAT_ID": "@mock_channel",
        "OPENAI_API_KEY": "mock_openai",
        "ELEVENLABS_API_KEY": "mock_eleven",
    })
    @patch("main.httpx.Client")
    def test_tts_failure_fallback_to_text(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        # Mock Telegram getChat
        mock_chat_resp = MagicMock(status_code=200)
        mock_chat_resp.json.return_value = {
            "result": {
                "pinned_message": {
                    "text": "1. pies - собака"
                }
            }
        }

        # Mock OpenAI chat completions
        mock_openai_resp = MagicMock(status_code=200)
        mock_openai_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"items": [{"word": "pies", "pl_sentence": "Pies szczeka.", "ru_translation": "Собака лает."}]}'
                    }
                }
            ]
        }

        # Mock ElevenLabs TTS failure (e.g. 429 rate limit or quota exceeded)
        mock_tts_resp = MagicMock(status_code=429, text="Quota exceeded")

        # Mock Telegram sendMessage
        mock_send_msg_resp = MagicMock(status_code=200)

        mock_client.post.side_effect = [
            mock_chat_resp,
            mock_openai_resp,
            mock_tts_resp,
            mock_send_msg_resp,
        ]

        response, status = send_vocab_task(MagicMock())
        self.assertEqual(status, 200)
        self.assertEqual(response, "Batch processed and sent successfully")
        # Check that sendMessage was called
        calls = mock_client.post.call_args_list
        last_call_url = calls[-1][0][0]
        self.assertIn("sendMessage", last_call_url)


if __name__ == "__main__":
    unittest.main()
