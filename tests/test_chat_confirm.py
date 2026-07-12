from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.models import User
from app.main import _is_confirming


class ConfirmIntentUnitTests(unittest.TestCase):
    """_is_confirming 单元测试：聚焦“长句确认”不再被判为非确认（死循环根因）。"""

    def test_long_sentence_confirmation_is_recognized(self):
        # 这些是会触发死循环的真实/近似确认消息
        loop_cases = [
            "就买「确认」，从我余额里扣钱吧",
            "就买「确认」，从我余额里扣钱。",
            "确认，从我余额里扣钱吧",
            "下单吧，从我余额扣",
            "那就确认下单，扣余额",
            "确认",
            "下单",
            "确认下单",
            "好的",
            "对",
            "行",
            "结账",
            "扣钱吧",
        ]
        for msg in loop_cases:
            self.assertTrue(_is_confirming(msg), f"应识别为确认: {msg!r}")

    def test_modify_and_negation_not_treated_as_confirm(self):
        cases = [
            "换一杯美式咖啡",
            "不要了",
            "不对",
            "太贵了，换一个",
            "买别的",
            "改主意了",
            "取消订单",
            "算了",
        ]
        for msg in cases:
            self.assertFalse(_is_confirming(msg), f"不应识别为确认: {msg!r}")

    def test_question_not_treated_as_confirm(self):
        cases = [
            "下单流程是怎样的？",
            "怎么下单？",
            "确认一下可以吗？",
            "能不能便宜点",
        ]
        for msg in cases:
            self.assertFalse(_is_confirming(msg), f"提问不应识别为确认: {msg!r}")

    def test_pure_coffee_name_or_chat_not_treated_as_confirm(self):
        cases = [
            "美式咖啡",
            "再来一杯",
            "",
        ]
        for msg in cases:
            self.assertFalse(_is_confirming(msg), f"非确认消息: {msg!r}")


# ---- 进程内替身（与 test_chat_order_view.py 保持一致的轻量实现）----
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

    def getdel(self, key):
        return self._strings.pop(key, None)

    def delete(self, key):
        self._strings.pop(key, None)
        self._lists.pop(key, None)
        return 1

    def expire(self, key, ttl):
        return True


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)

    def add(self, _obj):
        pass

    def commit(self):
        pass

    def refresh(self, _obj):
        pass

    def rollback(self):
        pass


class ConfirmEndpointTests(unittest.TestCase):
    def test_long_confirmation_places_order_instead_of_looping(self):
        """回归：带支付措辞的长句确认应真正下单（触发 place_orders），
        而不是再次要求确认、陷入死循环。"""
        from app import main as app_main
        from app.memory import chat_history

        fake_redis = _FakeRedis()
        fake_user = User()
        fake_user.user_id = 1
        fake_user.balance = Decimal("100.00")
        fake_session = _FakeSession([fake_user])

        pending = {"coffees": [{"name": "柑橘冷萃", "price": 28.0}], "total": 28.0}
        fake_order = SimpleNamespace(
            order_id=99, coffee_name="柑橘冷萃", amount=Decimal("28.00")
        )

        def _fake_get_db():
            yield fake_session

        with (
            patch.object(chat_history, "_client", lambda: fake_redis),
            patch.object(app_main, "place_orders", return_value=[fake_order]) as mock_place,
            patch.object(
                app_main,
                "current_account",
                return_value=SimpleNamespace(user_id=1, account_id=1, role="user"),
            ),
            patch.object(app_main, "_publish_web_restaurant_event", lambda *a, **k: None),
            patch.object(app_main, "_try_publish_visualization_event", lambda *a, **k: None),
        ):
            chat_history.set_pending_order(1, pending)
            app_main.app.dependency_overrides[app_main.get_db] = _fake_get_db
            try:
                client = TestClient(app_main.app)
                resp = client.post(
                    "/chat",
                    json={
                        "user_id": 1,
                        "message": "就买「确认」，从我余额里扣钱吧",
                        "request_id": "req-confirm-1",
                        "consumer_url": "http://127.0.0.1:8003/",
                    },
                )
            finally:
                app_main.app.dependency_overrides.pop(app_main.get_db, None)

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(
            mock_place.called,
            "确认消息应真正触发 place_orders 下单，而非再次要求确认",
        )
        reply = resp.json()["reply"]
        self.assertIn("已为您下单", reply)
        self.assertIn("柑橘冷萃", reply)
        self.assertNotIn("确认下单请回复", reply)


if __name__ == "__main__":
    unittest.main()
