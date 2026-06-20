from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from unittest.mock import patch

from app.db.models import Order
from app.main import _format_order_history_reply, _is_order_view_query


class _FakeRedis:
    """进程内 Redis 替身：只实现 chat_history 用到的 List/String 命令。"""

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

    def expire(self, key, ttl):
        return True

    def set(self, key, value):
        self._strings[key] = value
        return True

    def get(self, key):
        return self._strings.get(key)

    def delete(self, key):
        self._strings.pop(key, None)
        self._lists.pop(key, None)
        return 1


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.added = []

    def query(self, _model):
        return _FakeQuery(self._rows)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def flush(self):
        pass

    def refresh(self, _obj):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _make_order(order_id, name, amount, created_at):
    order = Order()
    order.order_id = order_id
    order.coffee_name = name
    order.amount = Decimal(str(amount))
    order.created_at = created_at
    return order


class OrderViewIntentTests(unittest.TestCase):
    def test_recognizes_order_view_phrases(self):
        cases = [
            "帮我看看最近订单。",
            "查看订单",
            "看看我的订单",
            "订单列表",
            "最近订单有哪些",
            "查一下订单记录",
            "我想看看历史订单",
        ]
        for msg in cases:
            self.assertTrue(_is_order_view_query(msg), msg)

    def test_does_not_match_recommendation_or_order_placement(self):
        cases = [
            "就买你刚才推荐的那杯，从我余额里扣钱吧。",
            "确认下单。",
            "结账吧。",
            "我想喝点清甜水果味的，但不要加牛奶，推荐一下。",
            "有没有椰子味的？不要太苦。",
            "如果可以，推荐冰饮。",
            "再来一杯。",
            "",
        ]
        for msg in cases:
            self.assertFalse(_is_order_view_query(msg), repr(msg))

    def test_empty_history_reply_is_friendly(self):
        reply = _format_order_history_reply(_FakeSession([]), user_id=1)
        self.assertIn("还没有订单", reply)
        self.assertNotIn("根据您的喜好", reply)

    def test_history_reply_lists_rows_and_total(self):
        rows = [
            _make_order(42, "柑橘冷萃", "28.00", datetime(2026, 6, 19, 14, 30)),
            _make_order(7, "美式咖啡", "22.00", datetime(2026, 6, 19, 10, 5)),
        ]
        reply = _format_order_history_reply(_FakeSession(rows), user_id=1)
        self.assertIn("您最近的订单", reply)
        self.assertIn("柑橘冷萃", reply)
        self.assertIn("#42", reply)
        self.assertIn("¥28.00", reply)
        self.assertIn("50.00", reply)
        self.assertIn("2 单合计", reply)
        self.assertNotIn("根据您的喜好", reply)

    def test_chat_endpoint_returns_orders_for_view_query(self):
        """端到端：/chat 收到「查看订单」时返回订单列表，而不是推荐文案。"""
        rows = [
            _make_order(42, "柑橘冷萃", "28.00", datetime(2026, 6, 19, 14, 30)),
            _make_order(7, "美式咖啡", "22.00", datetime(2026, 6, 19, 10, 5)),
        ]
        fake_session = _FakeSession(rows)
        fake_redis = _FakeRedis()

        from app import main as app_main
        from app.memory import chat_history

        def _fake_get_db():
            yield fake_session

        with (
            patch.object(chat_history, "_client", lambda: fake_redis),
        ):
            app_main.app.dependency_overrides[app_main.get_db] = _fake_get_db
            try:
                client = TestClient(app_main.app)
                resp = client.post(
                    "/chat",
                    json={
                        "user_id": 1,
                        "message": "帮我看看最近订单。",
                        "consumer_url": "http://127.0.0.1:8003/",
                    },
                )
            finally:
                app_main.app.dependency_overrides.pop(app_main.get_db, None)

        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        reply = body["reply"]
        self.assertIn("柑橘冷萃", reply)
        self.assertIn("#42", reply)
        self.assertNotIn("根据您的喜好", reply)
        self.assertNotIn("为您推荐", reply)

    def test_chat_endpoint_still_recommends_for_non_view_query(self):
        """回归保护：推荐/下单/确认类消息不会被查看订单分支拦截（纯逻辑判定）。"""
        non_view = [
            "推荐一杯清爽果味的。",
            "再来一杯。",
            "确认下单。",
            "就买柑橘冷萃。",
            "换一个口味。",
        ]
        for msg in non_view:
            self.assertFalse(
                _is_order_view_query(msg),
                f"推荐/下单消息不应被判定为查看订单: {msg!r}",
            )


if __name__ == "__main__":
    unittest.main()
