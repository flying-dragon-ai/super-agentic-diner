"""复购意图识别 + 历史订单解析测试。

覆盖：
  - detect_reorder_intent：识别"和之前一样/老样子/上次那杯"等复购意图
  - resolve_reorder_target：从历史订单按频次取最常点 + 画像偏好兜底
  - 空历史回退 None（不报错）
  - 否定守门（"和之前不一样"不触发复购）
"""
from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports
import unittest
from collections import Counter
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch


class _FakeOrderQuery:
    """模拟 Order 查询链：filter().filter().order_by().limit().all()"""

    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """按模型返回不同 fake query。"""

    def __init__(self, order_rows=None, profile_row=None):
        self._order_rows = order_rows or []
        self._profile_row = profile_row

    def query(self, model):
        # Order 模型按类名匹配
        if model.__name__ == "Order":
            return _FakeOrderQuery(self._order_rows)
        # UserProfile 返回 first()
        class _Q:
            def __init__(self, row):
                self._row = row

            def filter(self, *_a, **_k):
                return self

            def first(self):
                return self._row

        return _Q(self._profile_row)


def _make_order(coffee_name, days_ago=0):
    return SimpleNamespace(
        coffee_name=coffee_name,
        amount=28,
        payment_status="paid",
        user_id=100,
        created_at=datetime(2026, 6, 27),
    )


# ---------------- 测试 1：detect_reorder_intent ----------------


class DetectReorderIntentTests(unittest.TestCase):
    def test_reorder_phrases_detected(self):
        """复购触发短语应被识别为复购意图。"""
        from app.services.reorder_service import detect_reorder_intent

        reorder_msgs = [
            "和之前一样的吧",
            "还是来个和之前一样的吧",
            "老样子",
            "上次那杯",
            "和上次一样",
            "常点的那款",
            "我常喝的",
            "跟刚才一样",
        ]
        for msg in reorder_msgs:
            with self.subTest(msg=msg):
                self.assertTrue(detect_reorder_intent(msg), f"应识别为复购: {msg}")

    def test_normal_order_not_treated_as_reorder(self):
        """普通下单（含具体咖啡名或口味）不应识别为复购。"""
        from app.services.reorder_service import detect_reorder_intent

        normal_msgs = [
            "我要一杯美式咖啡",
            "来个苦的",
            "推荐一下果味的",
            "下单",
            "确认",
            "你好",
        ]
        for msg in normal_msgs:
            with self.subTest(msg=msg):
                self.assertFalse(detect_reorder_intent(msg), f"不应识别为复购: {msg}")

    def test_negation_blocks_reorder(self):
        """否定（和之前不一样/换一杯）不触发复购。"""
        from app.services.reorder_service import detect_reorder_intent

        negation_msgs = [
            "和之前不一样",
            "换个口味",
            "不要上次那个",
            "这次换一个",
        ]
        for msg in negation_msgs:
            with self.subTest(msg=msg):
                self.assertFalse(detect_reorder_intent(msg), f"否定不应触发复购: {msg}")


# ---------------- 测试 2：resolve_reorder_target 历史订单 ----------------


class ResolveReorderTargetTests(unittest.TestCase):
    def test_returns_most_frequent_from_history(self):
        """有历史订单时，返回点得最多的那杯（频次优先）。"""
        from app.services import reorder_service as rs

        # 美式咖啡点了3次，柑橘冷萃点了1次 → 应返回美式咖啡
        orders = [
            _make_order("美式咖啡"),
            _make_order("美式咖啡"),
            _make_order("美式咖啡"),
            _make_order("柑橘冷萃"),
        ]
        db = _FakeSession(order_rows=orders, profile_row=None)
        with patch.object(rs, "get_profile_hint", return_value=""):
            result = rs.resolve_reorder_target(db, user_id=100)
        self.assertEqual(result, "美式咖啡")

    def test_returns_none_when_no_history(self):
        """无历史订单时返回 None（让调用方回退到对话历史）。"""
        from app.services import reorder_service as rs

        db = _FakeSession(order_rows=[], profile_row=None)
        with patch.object(rs, "get_profile_hint", return_value=""):
            result = rs.resolve_reorder_target(db, user_id=100)
        self.assertIsNone(result)

    def test_frequency_tie_returns_most_recent(self):
        """频次相同时，返回最近下单的那杯。"""
        from app.services import reorder_service as rs

        # 两杯各点1次，柑橘冷萃更近（列表里靠前=更近，因查询按 created_at desc）
        orders = [
            _make_order("柑橘冷萃"),
            _make_order("美式咖啡"),
        ]
        db = _FakeSession(order_rows=orders, profile_row=None)
        with patch.object(rs, "get_profile_hint", return_value=""):
            result = rs.resolve_reorder_target(db, user_id=100)
        # 频次相同（1:1）→ 取最近下单的柑橘冷萃
        self.assertEqual(result, "柑橘冷萃")


if __name__ == "__main__":
    unittest.main()
