"""_is_clearly_non_order 单元测试：验证「跳过 parse_intent」启发式的边界。

目标：保证加速路径不会误判下单意图（漏判比多判更危险，漏判会少调一次 LLM
导致下不了单）。所以下单类消息必须返回 False，推荐/聊天类才允许返回 True。
"""
from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports

import unittest

from app.main import _is_clearly_non_order


class ClearlyNonOrderHeuristicTests(unittest.TestCase):
    def test_order_phrases_are_not_skipped(self):
        """含订单词的消息必须调 parse_intent（返回 False）。"""
        order_cases = [
            "来一杯美式",
            "我要一杯柑橘冷萃",
            "点一杯拿铁",
            "给我来个摩卡",
            "整一杯卡布奇诺",
            "买这个",
            "下单",
            "结账",
            "买单",
            "扣钱吧",
            "就这个",
            "就买这杯",
            "这两杯了",
            "就它了",
        ]
        for msg in order_cases:
            self.assertFalse(
                _is_clearly_non_order(msg),
                f"含订单词的消息不应跳过 parse_intent: {msg!r}",
            )

    def test_short_confirmations_are_not_skipped(self):
        """短确认词（在 _CONFIRM_WEAK 里）必须调 parse_intent。"""
        confirm_cases = ["好的", "好", "对", "是的", "没错", "可以", "行", "买"]
        for msg in confirm_cases:
            self.assertFalse(
                _is_clearly_non_order(msg),
                f"短确认词不应跳过 parse_intent: {msg!r}",
            )

    def test_strong_confirmations_are_not_skipped(self):
        """强确认词（任意长度）必须调 parse_intent。"""
        strong_cases = [
            "确认",
            "确认下单",
            "从我余额扣钱",
            "下单吧",
            "结账，谢谢",
        ]
        for msg in strong_cases:
            self.assertFalse(
                _is_clearly_non_order(msg),
                f"强确认消息不应跳过 parse_intent: {msg!r}",
            )

    def test_recommend_requests_are_safely_skipped(self):
        """明确求推荐/聊天的消息可以跳过 parse_intent（省 1 次 LLM 调用）。"""
        recommend_cases = [
            "推荐一杯清爽果味的",
            "有什么推荐",
            "介绍一下拿铁",
            "美式和拿铁的区别",
            "哪种不苦",
            "换口味",
            "我想喝果味的",
            "不要太苦",
            "果味推荐一下",
            "椰香的有没有",
        ]
        for msg in recommend_cases:
            self.assertTrue(
                _is_clearly_non_order(msg),
                f"推荐/聊天消息应跳过 parse_intent: {msg!r}",
            )

    def test_chat_questions_are_safely_skipped(self):
        """问号/询问类消息可以跳过 parse_intent。"""
        question_cases = [
            "几点关门？",
            "多少钱？",
            "可以加冰吗",
            "为什么这么贵",
            "怎么点单",
        ]
        for msg in question_cases:
            self.assertTrue(
                _is_clearly_non_order(msg),
                f"询问类消息应跳过 parse_intent: {msg!r}",
            )

    def test_flavor_descriptions_are_safely_skipped(self):
        """口味描述词（无订单词）可以跳过 parse_intent。"""
        flavor_cases = [
            "我喜欢苦一点的",
            "清爽一点的",
            "忌口牛奶",
            "深烘的",
            "加冰的",
        ]
        for msg in flavor_cases:
            self.assertTrue(
                _is_clearly_non_order(msg),
                f"口味描述应跳过 parse_intent: {msg!r}",
            )

    def test_empty_message_is_skipped(self):
        """空消息不会下单，安全跳过。"""
        self.assertTrue(_is_clearly_non_order(""))
        self.assertTrue(_is_clearly_non_order("   "))

    def test_ambiguous_coffee_name_keeps_safe(self):
        """纯咖啡名（无订单词、无推荐词）→ 保守返回 False，调 LLM 兜底。"""
        ambiguous_cases = [
            "美式咖啡",
            "柑橘冷萃",
            "拿铁",
        ]
        for msg in ambiguous_cases:
            self.assertFalse(
                _is_clearly_non_order(msg),
                f"纯咖啡名应保守调 parse_intent: {msg!r}",
            )


if __name__ == "__main__":
    unittest.main()
