"""Regression tests for chat_history Redis failure tolerance.

Locks the fix for the bug where a Redis timeout (``redis.exceptions.TimeoutError``
≈ 56s hang on a flaky cloud Redis) bubbled up from ``get_history`` /
``get_pending_order`` to ``/chat`` and returned a 500. With the fix, Redis
failures degrade instead:

* reads return an empty state (``[]`` / ``None``)
* writes are swallowed (best-effort)

so the chat / ordering path never crashes on Redis being unreachable.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from redis.exceptions import TimeoutError

from app.memory import chat_history


def _raising_client():
    raise TimeoutError("simulated redis socket timeout")


class ChatHistoryFallbackTests(unittest.TestCase):
    """Forces every ``_client()`` call to raise a Redis timeout, then asserts
    each public function degrades rather than propagating the exception."""

    def setUp(self):
        patcher = patch.object(chat_history, "_client", side_effect=_raising_client)
        self._mock_client = patcher.start()
        self.addCleanup(patcher.stop)

    def test_get_history_returns_empty_on_timeout(self):
        self.assertEqual(chat_history.get_history(1), [])

    def test_get_pending_order_returns_none_on_timeout(self):
        self.assertIsNone(chat_history.get_pending_order(1))

    def test_add_message_swallows_timeout(self):
        # Must not raise — writing memory is best-effort.
        chat_history.add_message(1, "user", "hi")

    def test_set_pending_order_swallows_timeout(self):
        chat_history.set_pending_order(1, {"coffees": [{"name": "美式咖啡", "price": 22.0}]})

    def test_clear_pending_order_swallows_timeout(self):
        chat_history.clear_pending_order(1)

    def test_clear_history_swallows_timeout(self):
        chat_history.clear_history(1)

    def test_every_function_was_actually_exercised_through_client(self):
        # Sanity check: the simulated timeout path really fired for the read API.
        chat_history.get_history(1)
        chat_history.get_pending_order(1)
        self.assertGreaterEqual(self._mock_client.call_count, 2)


if __name__ == "__main__":
    unittest.main()
