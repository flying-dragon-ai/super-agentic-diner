from __future__ import annotations

import unittest

from app.config import settings
from app.llm import client as llm


class LlmConfigurationTests(unittest.TestCase):
    def setUp(self):
        self._settings = {
            "llm_api_key": settings.llm_api_key,
            "deepseek_api_key": settings.deepseek_api_key,
            "openai_api_key": settings.openai_api_key,
            "llm_base_url": settings.llm_base_url,
        }

    def tearDown(self):
        for key, value in self._settings.items():
            setattr(settings, key, value)

    def test_blank_keys_keep_llm_inactive_with_missing_reason(self):
        settings.llm_api_key = ""
        settings.deepseek_api_key = ""
        settings.openai_api_key = ""

        self.assertFalse(llm.has_real_key())
        self.assertEqual(settings.effective_llm_api_key, "")
        self.assertIsNone(settings.llm_api_key_source)
        self.assertEqual(settings.llm_status_reason, "missing_api_key")

    def test_deepseek_api_key_alias_activates_llm(self):
        settings.llm_api_key = ""
        settings.deepseek_api_key = "ds-real-key"
        settings.openai_api_key = ""

        self.assertTrue(llm.has_real_key())
        self.assertEqual(settings.effective_llm_api_key, "ds-real-key")
        self.assertEqual(settings.llm_api_key_source, "DEEPSEEK_API_KEY")
        self.assertEqual(settings.llm_status_reason, "configured")

    def test_openai_api_key_alias_activates_llm(self):
        settings.llm_api_key = ""
        settings.deepseek_api_key = ""
        settings.openai_api_key = "openai-real-key"

        self.assertTrue(llm.has_real_key())
        self.assertEqual(settings.effective_llm_api_key, "openai-real-key")
        self.assertEqual(settings.llm_api_key_source, "OPENAI_API_KEY")

    def test_llm_api_key_takes_precedence_over_aliases(self):
        settings.llm_api_key = "primary-real-key"
        settings.deepseek_api_key = "deepseek-real-key"
        settings.openai_api_key = "openai-real-key"

        self.assertTrue(llm.has_real_key())
        self.assertEqual(settings.effective_llm_api_key, "primary-real-key")
        self.assertEqual(settings.llm_api_key_source, "LLM_API_KEY")

    def test_placeholder_key_is_not_active(self):
        settings.llm_api_key = "sk-your-key-here"
        settings.deepseek_api_key = ""
        settings.openai_api_key = ""

        self.assertFalse(llm.has_real_key())
        self.assertEqual(settings.llm_status_reason, "placeholder_or_invalid_api_key")

    def test_chat_completions_url_accepts_base_or_full_endpoint(self):
        settings.llm_base_url = "https://api.example.test/v1"
        self.assertEqual(
            llm._chat_completions_url(),
            "https://api.example.test/v1/chat/completions",
        )

        settings.llm_base_url = "https://api.example.test/v1/chat/completions"
        self.assertEqual(
            llm._chat_completions_url(),
            "https://api.example.test/v1/chat/completions",
        )


if __name__ == "__main__":
    unittest.main()
