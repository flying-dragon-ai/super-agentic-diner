"""推荐 Agent(推荐)：RAG 检索 + 硬过滤 + LLM 生成 + 历史经验融合。

职责：
  1. 关键词提取 + RAG 检索候选咖啡（复用现有 chat_service 逻辑）
  2. ★ 硬过滤：从经验中提取规则，直接剔除已知错项（100% 不再犯同样错误）
  3. 从经验继承 Agent 读取历史教训，融合到推荐上下文（LLM 软引导）
  4. 用 RECOMMENDER_PROMPT 生成有理由的推荐
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import Product
from app.llm import client as llm
from app.rag.keywords import extract_keywords
from app.rag.retrieval import retrieve
from app.services.agents.experience_agent import get_experience_for_user, get_hard_filters
from app.services.user_profile_service import get_profile_summary


def get_profile_hint(user_id: int) -> str:
    """读取用户画像摘要（推荐软引导用）。无画像返回空字符串。

    复用 user_profile_service.get_profile_summary，独立 session 读取避免污染调用方。
    """
    try:
        return get_profile_summary(user_id)
    except Exception:
        logger.warning("读取用户画像失败 user_id=%s", user_id, exc_info=True)
        return ""

logger = logging.getLogger(__name__)


def _apply_hard_filters(
    candidates: list[Product],
    filters: dict,
) -> tuple[list[Product], list[str]]:
    """对 RAG 候选列表应用硬过滤，返回（过滤后列表, 被剔除的咖啡名列表）。

    过滤规则：
      1. banned_names：直接按名字拉黑
      2. banned_tags：按 product.tags 匹配，含被禁 tag 的剔除
    如果过滤后为空（全部被拉黑），返回原始列表（宁可不过滤也不返回空）。
    """
    banned_names = set(filters.get("banned_names", []))
    banned_tags = set(filters.get("banned_tags", []))

    if not banned_names and not banned_tags:
        return candidates, []

    survived: list[Product] = []
    removed: list[str] = []

    for product in candidates:
        # 规则1：名字在黑名单
        if product.name in banned_names:
            removed.append(product.name)
            continue
        # 规则2：tags 含被禁标签
        product_tags = set(str(product.tags or "").split(","))
        hit_tags = product_tags & banned_tags
        if hit_tags:
            removed.append(f"{product.name}(命中:{','.join(hit_tags)})")
            continue
        survived.append(product)

    # 全被过滤 → 回退原始列表（不能让用户无候选可选）
    if not survived and candidates:
        logger.info("硬过滤剔除全部候选，回退原始列表（%d 个）", len(candidates))
        return candidates, []

    return survived, removed


def recommend(
    db: Session,
    user_id: int,
    user_msg: str,
    history: list[dict],
) -> dict:
    """生成推荐回复。

    返回：
        {
            "reply": str,               # 给用户的回复
            "candidates": [Product],    # 过滤后的候选咖啡列表
            "context": str,             # 拼接的咖啡知识上下文
            "applied_experience": bool, # 是否引用了历史经验（软引导）
            "hard_filtered": list[str], # 被硬过滤剔除的咖啡名（供事件展示）
        }
    """
    # 第1步：RAG 检索（关键词提取 → 正向 LIKE 召回 → 负向 NOT LIKE 过滤）
    positive, negative = extract_keywords(user_msg)
    kb_rows = retrieve(db, positive, negative)
    # 兜底：RAG 无结果 → 加载全部真实产品，杜绝 LLM(大模型) 幻觉
    if not kb_rows:
        from app.services.chat_service import get_all_products
        kb_rows = get_all_products(db)

    # 第2步：★ 硬过滤 — 从经验提取规则，直接剔除已知错项
    hard_filters = get_hard_filters(user_id)
    kb_rows, hard_filtered = _apply_hard_filters(kb_rows, hard_filters)
    if hard_filtered:
        logger.info("用户 %d 硬过滤剔除: %s", user_id, hard_filtered)

    # 第3步：拼接咖啡知识上下文（只用过滤后的候选）
    context_parts = [
        f"{r.name}（¥{r.base_price}）：{r.description}" for r in kb_rows
    ]
    context = "\n---\n".join(context_parts)

    # 第4步：读取历史经验（软引导：注入提示词，LLM 大概率遵守）
    # 4a. 用户画像（正向偏好，来自 chat+order 的 LLM 归纳摘要）
    profile_hint = get_profile_hint(user_id)
    # 4b. 历史经验（反向教训：不要什么，来自复盘 Agent）
    experience_text = get_experience_for_user(user_id)

    guidance_parts: list[str] = []
    if profile_hint:
        guidance_parts.append(f"《用户画像·推荐前必读》\n{profile_hint}")
    if experience_text:
        guidance_parts.append(f"《历史经验·推荐前必读》\n{experience_text}")
    applied_experience = bool(guidance_parts)

    if guidance_parts:
        context = "\n\n".join(guidance_parts) + f"\n\n《咖啡风味手册》相关段落：\n{context}"
    else:
        context = f"《咖啡风味手册》相关段落：\n{context}"

    # 第5步：调 LLM 生成推荐（用推荐 Agent 专属提示词，只能看到过滤后的候选）
    reply = llm.chat_with_role(
        system_prompt=llm.RECOMMENDER_PROMPT,
        context=context,
        history=history,
        user_msg=user_msg,
    )
    # LLM 不可用时降级：根据是否有候选给不同的友好回复
    if not reply:
        if kb_rows:
            names = "、".join(r.name for r in kb_rows[:3])
            reply = f"好嘞~根据您的喜好，推荐这几款：{names}。想试试哪一杯？告诉我名字就可以下单啦~"
        else:
            reply = "您好~我是 Crossroads Agent Café AI 店长 ☕ 今天想喝点什么口味的？可以告诉我喜欢的风味或者忌口，我来帮您挑一杯~"

    return {
        "reply": reply,
        "candidates": kb_rows,
        "context": context,
        "applied_experience": applied_experience,
        "hard_filtered": hard_filtered,
    }
