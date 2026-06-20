"""Agent 编排器：按序协调店长 / 推荐 / 复盘 / 经验继承四个 Agent。

被 /chat 调用，替代原来直接调 parse_intent + chat_service 的散装逻辑。
编排流程：
  1. 店长 Agent 意图分析 → order / recommend / chat
  2. 检测纠正信号 → 若是，复盘 Agent 分析失误 + 经验继承存储
  3. recommend → 推荐 Agent（融合经验）生成回复
  4. chat → 复用店长回复（或降级 chat_service）
  5. order → 不在此处理，返回意图由 main.py 继续下单流程

返回 OrchestratorResult，main.py 据此执行下单 / 回复 + 发可视化事件。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.memory.chat_history import add_message, get_history
from app.services.agents import manager_agent, recommender_agent, reviewer_agent

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """编排器返回给 /chat 的结构化结果。"""

    intent: str = "chat"
    reply: str = ""
    # Agent 协作元数据（供 main.py 发可视化事件）
    events: list[dict[str, Any]] = field(default_factory=list)
    # 复盘结果（检测到纠正时填充）
    review: dict[str, Any] | None = None
    applied_experience: bool = False


def orchestrate(
    db: Session,
    user_id: int,
    user_msg: str,
    *,
    correlation_id: str | None = None,
) -> OrchestratorResult:
    """多 Agent(智能体) 协作主入口。

    副作用：会写 Redis 对话历史（add_message），与原 /chat 行为一致。
    """
    result = OrchestratorResult()
    history = get_history(user_id)

    # ===== 第1步：店长 Agent 意图分析 =====
    intent_data = manager_agent.parse_intent(history, user_msg)
    intent = intent_data.get("intent", "chat")
    result.intent = intent
    result.events.append(
        {
            "type": "agent.manager.intent",
            "payload": {"user_id": user_id, "intent": intent, "reason": intent_data.get("reason", "")},
        }
    )

    # ===== 第2步：纠正检测 → 触发复盘 Agent =====
    if manager_agent.detect_correction(user_msg, history):
        result.events.append(
            {
                "type": "agent.reviewer.reviewing",
                "payload": {"user_id": user_id, "trigger": "correction_detected"},
            }
        )
        review = reviewer_agent.review_mistake(
            db,
            user_id=user_id,
            user_msg=user_msg,
            history=history,
            correlation_id=correlation_id,
        )
        if review:
            result.review = review
            result.events.append(
                {
                    "type": "agent.reviewer.reviewed",
                    "payload": {
                        "user_id": user_id,
                        "mistake_type": review.get("mistake_type"),
                        "rating": review.get("rating"),
                        "insight": review.get("insight"),
                    },
                }
            )
            result.events.append(
                {
                    "type": "agent.experience.learned",
                    "payload": {"user_id": user_id, "insight": review.get("insight", "")},
                }
            )

    # ===== 第3步：按意图分派 =====
    if intent == "order":
        # order 意图不在此处理回复，main.py 继续走下单流程
        return result

    if intent == "recommend":
        # 推荐 Agent：RAG + 经验融合 → 生成推荐
        result.events.append(
            {
                "type": "agent.recommender.suggesting",
                "payload": {"user_id": user_id},
            }
        )
        reco = recommender_agent.recommend(db, user_id, user_msg, history)
        result.reply = reco["reply"]
        result.applied_experience = reco["applied_experience"]
        result.events.append(
            {
                "type": "agent.recommender.suggested",
                "payload": {
                    "user_id": user_id,
                    "applied_experience": reco["applied_experience"],
                    "candidate_count": len(reco["candidates"]),
                },
            }
        )
        if reco["applied_experience"]:
            result.events.append(
                {
                    "type": "agent.experience.applied",
                    "payload": {"user_id": user_id},
                }
            )
        # 写对话历史
        add_message(user_id, "user", user_msg)
        add_message(user_id, "assistant", result.reply)
        return result

    # ===== chat 意图：复用推荐 Agent（闲聊也能给点建议） =====
    reco = recommender_agent.recommend(db, user_id, user_msg, history)
    result.reply = reco["reply"]
    result.applied_experience = reco["applied_experience"]
    result.events.append(
        {
            "type": "agent.recommender.suggested",
            "payload": {
                "user_id": user_id,
                "intent": "chat",
                "applied_experience": reco["applied_experience"],
            },
        }
    )
    add_message(user_id, "user", user_msg)
    add_message(user_id, "assistant", result.reply)
    return result
