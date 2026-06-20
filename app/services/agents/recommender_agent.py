"""推荐 Agent(推荐)：RAG 检索 + LLM 生成 + 历史经验融合。

职责：
  1. 关键词提取 + RAG 检索候选咖啡（复用现有 chat_service 逻辑）
  2. 从经验继承 Agent 读取该用户的历史教训，融合到推荐上下文
  3. 用 RECOMMENDER_PROMPT 生成有理由的推荐
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Product
from app.llm import client as llm
from app.rag.keywords import extract_keywords
from app.rag.retrieval import retrieve
from app.services.agents.experience_agent import get_experience_for_user


def recommend(
    db: Session,
    user_id: int,
    user_msg: str,
    history: list[dict],
) -> dict:
    """生成推荐回复。

    返回：
        {
            "reply": str,            # 给用户的回复
            "candidates": [Product], # 候选咖啡列表
            "context": str,          # 拼接的咖啡知识上下文
            "applied_experience": bool,  # 是否引用了历史经验
        }
    """
    # 第1步：RAG 检索（关键词提取 → 正向 LIKE 召回 → 负向 NOT LIKE 过滤）
    positive, negative = extract_keywords(user_msg)
    kb_rows = retrieve(db, positive, negative)
    # 兜底：RAG 无结果 → 加载全部真实产品，杜绝 LLM(大模型) 幻觉
    if not kb_rows:
        kb_rows = db.query(Product).order_by(Product.base_price).all()

    # 第2步：拼接咖啡知识上下文
    context_parts = [
        f"{r.name}（¥{r.base_price}）：{r.description}" for r in kb_rows
    ]
    context = "\n---\n".join(context_parts)

    # 第3步：读取历史经验（经验继承 Agent 提供）
    experience_text = get_experience_for_user(user_id)
    applied_experience = False
    if experience_text:
        context = f"《历史经验·推荐前必读》\n{experience_text}\n\n《咖啡风味手册》相关段落：\n{context}"
        applied_experience = True
    else:
        context = f"《咖啡风味手册》相关段落：\n{context}"

    # 第4步：调 LLM 生成推荐（用推荐 Agent 专属提示词）
    reply = llm.chat_with_role(
        system_prompt=llm.RECOMMENDER_PROMPT,
        context=context,
        history=history,
        user_msg=user_msg,
    )
    # LLM 不可用时降级
    if not reply:
        if kb_rows:
            reply = "根据您的喜好，为您推荐：" + context + "\n\n请问想点哪一杯呢？"
        else:
            reply = "您好，我是咖啡馆 AI 店长！请问您想喝什么口味的咖啡？"

    return {
        "reply": reply,
        "candidates": kb_rows,
        "context": context,
        "applied_experience": applied_experience,
    }
