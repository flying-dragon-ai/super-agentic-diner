"""复盘 Agent(事后复盘)：当用户表达「不是我要的 / 判断失误」时触发。

职责：
  1. 分析上一轮推荐 vs 用户实际想要什么 → 定位失误类型
  2. 调 LLM(大模型) 生成结构化教训 JSON
  3. 调经验继承 Agent 压缩成简短提示并双写存储

触发条件：由店长 Agent 的 detect_correction() 判定后，由编排器调用本 Agent。
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.llm import client as llm
from app.services.agents import experience_agent

logger = logging.getLogger(__name__)


def review_mistake(
    db: Session,
    *,
    user_id: int,
    user_msg: str,
    history: list[dict],
    correlation_id: str | None = None,
    trigger_reason: str = "correction",
) -> dict | None:
    """分析一次 AI(人工智能) 判断失误，生成并存储经验。

    参数 trigger_reason：触发原因（correction/anger/repeat），影响 LLM 分析侧重。
      - correction：推荐方向错误 → 分析口味误判
      - anger：用户情绪恶化 → 分析服务体验问题
      - repeat：用户重复提问 → 分析 AI 为何没理解

    返回复盘结果 dict（供编排器发可视化事件）；LLM 不可用时返回 None。
    """
    if not llm.has_real_key():
        logger.info("复盘 Agent(事后复盘) 跳过：无 LLM(大模型) key")
        return None

    # 第1步：提取上一轮推荐内容（最近 1-2 条 assistant 消息）
    recent_bot = [
        m.get("content", "")
        for m in (history or [])
        if m.get("role") == "assistant"
    ][:2]
    last_recommendation = "\n".join(recent_bot) if recent_bot else "（无推荐记录）"

    # 根据触发原因调整上下文描述
    trigger_desc = {
        "correction": "用户在纠正推荐方向（推荐了不对的咖啡）",
        "anger": "用户表达不满/生气情绪（体验差）",
        "repeat": "用户重复了上一轮的话（AI 没理解需求）",
    }.get(trigger_reason, "用户反馈异常")

    # 第2步：调 LLM 分析失误（用复盘 Agent 专属提示词）
    context = f"触发原因：{trigger_desc}\n上一轮 AI(人工智能) 回复内容：\n{last_recommendation}"
    raw = llm.chat_with_role(
        system_prompt=llm.REVIEWER_PROMPT,
        context=context,
        history=[],
        user_msg=user_msg,
        timeout_seconds=settings.llm_review_timeout_seconds,
    )
    result = llm.parse_json_response(raw)
    if not result or "insight" not in result:
        logger.warning("复盘 Agent LLM 输出解析失败: %s", raw[:120] if raw else "(empty)")
        return None

    # 第3步：调经验继承 Agent 把教训压缩成简短提示
    insight_text = result.get("insight", "")
    synthesized = llm.chat_with_role(
        system_prompt=llm.EXPERIENCE_SYNTHESIS_PROMPT,
        context=f"失误类型={result.get('mistake_type','')}\n用户实际想要={result.get('user_wanted','')}\n建议={insight_text}",
        history=[],
        user_msg="请压缩成推荐前必读提示",
        timeout_seconds=settings.llm_review_timeout_seconds,
    )
    final_insight = synthesized.strip() if synthesized else insight_text

    # 第4步：双写 MySQL + Redis
    experience_agent.save_experience(
        db,
        user_id=user_id,
        agent_role="reviewer",
        insight=final_insight,
        coffee_name=result.get("recommended_item"),
        context_tags=result.get("user_wanted", ""),
        rating=result.get("rating"),
        correlation_id=correlation_id,
    )

    return {
        "mistake_type": result.get("mistake_type", "unknown"),
        "recommended_item": result.get("recommended_item", ""),
        "user_wanted": result.get("user_wanted", ""),
        "insight": final_insight,
        "rating": result.get("rating"),
    }
