"""复盘 Agent 触发与道歉回复测试。

覆盖两个修复点：
  A. chat_with_role 接受 timeout_seconds 参数（原签名缺失 → TypeError → 复盘静默失败）
  B. 用户说"不对"/生气时，编排器同步复盘并回复道歉语（原后台线程跑，不影响回复）
"""
from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.llm import client as llm
from app.services import agent_orchestrator
from app.services.agents import reviewer_agent


class ChatWithRoleSignatureTests(unittest.TestCase):
    """修复点 A：chat_with_role 必须接受 timeout_seconds 关键字参数。"""

    def test_chat_with_role_accepts_timeout_seconds_without_type_error(self):
        # 无 key 时直接返回 ""，不会真正调 LLM，但必须接受 timeout_seconds 不报 TypeError
        with patch.object(llm, "has_real_key", return_value=False):
            # 修复前：TypeError: unexpected keyword argument 'timeout_seconds'
            # 修复后：正常返回 ""
            result = llm.chat_with_role(
                system_prompt="any",
                context="any",
                history=[],
                user_msg="hi",
                timeout_seconds=6.0,
            )
        self.assertEqual(result, "")


class ReviewApologyReplyTests(unittest.TestCase):
    """修复点 B：触发纠正/生气时，编排器回复道歉语而非继续推荐。"""

    def _fake_session(self):
        return SimpleNamespace(
            query=lambda _m: SimpleNamespace(
                filter=lambda *a, **k: SimpleNamespace(
                    order_by=lambda *a, **k: SimpleNamespace(all=lambda: [])
                )
            ),
            add=lambda _o: None,
            commit=lambda: None,
            rollback=lambda: None,
        )

    def test_correction_triggers_apology_reply(self):
        """用户在收到推荐后说"不对" → 编排器回复道歉语，不走推荐 Agent。"""
        history_with_recommendation = [
            {"role": "assistant", "content": "推荐 热美式（¥20.00）：双份浓缩加热水，干净纯粹"},
        ]
        apology_marker = "不好的体验"

        with (
            patch.object(
                agent_orchestrator, "get_history", return_value=history_with_recommendation
            ),
            patch.object(agent_orchestrator, "add_message", lambda *a, **k: None),
            # 无精确产品命中（"不对"不含产品名）
            patch.object(agent_orchestrator, "get_all_products", return_value=[]),
            # 复盘 Agent 的 LLM 调用：返回有效 JSON（修好 A 后能跑通）
            patch.object(reviewer_agent, "review_mistake", return_value={"insight": "误判口味"}),
            patch.object(
                agent_orchestrator.recommender_agent,
                "recommend",
                side_effect=AssertionError("触发纠正时不应再走推荐 Agent"),
            ),
        ):
            result = agent_orchestrator.orchestrate(
                self._fake_session(),
                user_id=888,
                user_msg="不对",
                precomputed_intent={"intent": "recommend", "reason": "test"},
            )

        # 回复必须是道歉语，而不是推荐内容
        self.assertIn(apology_marker, result.reply)
        # 复盘结果应填充
        self.assertIsNotNone(result.review)

    def test_anger_triggers_apology_reply(self):
        """用户表达生气情绪 → 编排器回复道歉语。"""
        apology_marker = "不好的体验"

        with (
            patch.object(agent_orchestrator, "get_history", return_value=[]),
            patch.object(agent_orchestrator, "add_message", lambda *a, **k: None),
            patch.object(agent_orchestrator, "get_all_products", return_value=[]),
            patch.object(reviewer_agent, "review_mistake", return_value={"insight": "体验差"}),
            patch.object(
                agent_orchestrator.recommender_agent,
                "recommend",
                side_effect=AssertionError("触发生气时不应再走推荐 Agent"),
            ),
        ):
            result = agent_orchestrator.orchestrate(
                self._fake_session(),
                user_id=889,
                user_msg="太烂了，什么破推荐",
                precomputed_intent={"intent": "recommend", "reason": "test"},
            )

        self.assertIn(apology_marker, result.reply)


if __name__ == "__main__":
    unittest.main()
