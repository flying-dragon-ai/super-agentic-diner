from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports
import unittest
import time

from app.config import settings
from app.llm import client as llm


class LlmConfigurationTests(unittest.TestCase):
    def setUp(self):
        self._settings = {
            "llm_api_key": settings.llm_api_key,
            "deepseek_api_key": settings.deepseek_api_key,
            "openai_api_key": settings.openai_api_key,
            "llm_base_url": settings.llm_base_url,
            "llm_connect_timeout_seconds": settings.llm_connect_timeout_seconds,
            "llm_intent_timeout_seconds": settings.llm_intent_timeout_seconds,
            "llm_generation_timeout_seconds": settings.llm_generation_timeout_seconds,
            "llm_review_timeout_seconds": settings.llm_review_timeout_seconds,
        }

    def tearDown(self):
        for key, value in self._settings.items():
            setattr(settings, key, value)
        llm.reset_client()

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

    def test_llm_timeout_settings_are_used_for_timeout_objects(self):
        settings.llm_connect_timeout_seconds = 1.5
        timeout = llm._timeout(7.0)

        self.assertEqual(timeout.connect, 1.5)
        self.assertEqual(timeout.read, 7.0)
        self.assertEqual(timeout.write, 7.0)
        self.assertEqual(timeout.pool, 7.0)

    def test_parse_intent_degrades_when_llm_times_out(self):
        settings.llm_api_key = "real-key"
        settings.deepseek_api_key = ""
        settings.openai_api_key = ""

        def _raise_timeout(*_args, **_kwargs):
            raise TimeoutError("simulated slow provider")

        original = llm._call_llm
        try:
            llm._call_llm = _raise_timeout
            self.assertEqual(llm.parse_intent([], "来一杯美式咖啡")["intent"], "order")
        finally:
            llm._call_llm = original

    def test_call_llm_enforces_wall_clock_budget(self):
        settings.llm_api_key = "real-key"
        settings.deepseek_api_key = ""
        settings.openai_api_key = ""

        def _slow_post(*_args, **_kwargs):
            time.sleep(0.2)
            return "too late"

        original = llm._post_chat_completion
        try:
            llm._post_chat_completion = _slow_post
            started = time.perf_counter()
            with self.assertRaises(TimeoutError):
                llm._call_llm([{"role": "user", "content": "hi"}], timeout_seconds=0.05)
            self.assertLess(time.perf_counter() - started, 0.15)
        finally:
            llm._post_chat_completion = original


if __name__ == "__main__":
    unittest.main()
