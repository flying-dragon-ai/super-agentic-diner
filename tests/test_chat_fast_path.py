from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


class _FakeRedis:
    def __init__(self):
        self._lists = {}
        self._strings = {}

    def lpush(self, key, value):
        self._lists.setdefault(key, []).insert(0, value)

    def lrange(self, key, start, end):
        data = self._lists.get(key, [])
        if end == -1:
            return list(data[start:])
        return list(data[start:end + 1])

    def ltrim(self, key, start, end):
        data = self._lists.get(key, [])
        self._lists[key] = list(data[start:end + 1])

    def set(self, key, value):
        self._strings[key] = value
        return True

    def get(self, key):
        return self._strings.get(key)

    def delete(self, key):
        self._strings.pop(key, None)
        self._lists.pop(key, None)
        return 1

    def expire(self, key, ttl):
        return True


class _FakeProductQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, products):
        self._products = products

    def query(self, _model):
        return _FakeProductQuery(self._products)

    def add(self, _obj):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


class ChatFastPathTests(unittest.TestCase):
    def test_exact_product_order_skips_llm_intent_call(self):
        from app import main as app_main
        from app.memory import chat_history

        product = SimpleNamespace(name="美式咖啡", base_price=Decimal("22.00"))
        fake_session = _FakeSession([product])
        fake_redis = _FakeRedis()

        def _fake_get_db():
            yield fake_session

        with (
            patch.object(chat_history, "_client", lambda: fake_redis),
            patch.object(app_main.llm, "parse_intent", side_effect=AssertionError("LLM should not be called")),
            patch.object(app_main, "_lookup_price_from_product", return_value=22.0),
            patch.object(app_main, "_publish_web_restaurant_event", lambda *a, **k: None),
            patch.object(app_main, "_try_publish_visualization_event", lambda *a, **k: None),
        ):
            app_main.app.dependency_overrides[app_main.get_db] = _fake_get_db
            try:
                client = TestClient(app_main.app)
                resp = client.post(
                    "/chat",
                    json={
                        "user_id": 1,
                        "message": "我要一杯美式咖啡",
                        "request_id": "req-fast-1",
                        "consumer_url": "https://consumer.invalid/",
                    },
                )
            finally:
                app_main.app.dependency_overrides.pop(app_main.get_db, None)

        self.assertEqual(resp.status_code, 200, resp.text)
        reply = resp.json()["reply"]
        self.assertIn("美式咖啡", reply)
        self.assertIn("确认下单", reply)


if __name__ == "__main__":
    unittest.main()
