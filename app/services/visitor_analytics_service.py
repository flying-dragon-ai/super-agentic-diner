"""访客分析服务：实时记录访客、分析下单/流失原因、通过自进化系统沉淀洞察。

职责：
  1. record_visit()：用户发消息时记录/更新今日访客记录
  2. mark_ordered()：用户下单成功后标记转化
  3. analyze_churn_async()：后台异步分析未下单访客的流失原因（LLM + experience_agent 三写）
  4. get_daily_analytics()：聚合当天访客统计数据
  5. get_churn_analysis()：聚合流失原因分类
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Order, VisitorInsight

logger = logging.getLogger(__name__)


def _today_start() -> datetime:
    """返回今天 UTC 0:00 的 datetime。"""
    return datetime.combine(date.today(), datetime.min.time())


def record_visit(
    db: Session,
    *,
    user_id: int,
    message: str,
    intent: str = "browse",
) -> VisitorInsight:
    """记录或更新今日访客记录。

    每个 user_id 每天一条记录；后续消息更新 message_count 和 last_message。
    意图优先级：order > recommend > chat > browse（不会被低优先级覆盖高优先级）。
    """
    today = _today_start()
    row = (
        db.query(VisitorInsight)
        .filter(
            VisitorInsight.user_id == user_id,
            VisitorInsight.visit_date >= today,
        )
        .first()
    )
    if row is None:
        row = VisitorInsight(
            user_id=user_id,
            visit_date=datetime.utcnow(),
            first_message=message[:200],
            last_message=message[:200],
            message_count=1,
            primary_intent=intent,
            ordered=0,
        )
        db.add(row)
    else:
        row.message_count += 1
        row.last_message = message[:200]
        # 意图升级：order > recommend > chat > browse
        _priority = {"browse": 0, "chat": 1, "recommend": 2, "order": 3}
        if _priority.get(intent, 0) > _priority.get(row.primary_intent, 0):
            row.primary_intent = intent
    db.commit()
    db.refresh(row)
    return row


def update_visit_intent(db: Session, user_id: int, intent: str) -> None:
    """更新访客的意图（由 /chat 意图识别后调用）。"""
    today = _today_start()
    row = (
        db.query(VisitorInsight)
        .filter(
            VisitorInsight.user_id == user_id,
            VisitorInsight.visit_date >= today,
        )
        .first()
    )
    if row is None:
        return
    _priority = {"browse": 0, "chat": 1, "recommend": 2, "order": 3}
    if _priority.get(intent, 0) > _priority.get(row.primary_intent, 0):
        row.primary_intent = intent
        db.commit()


def mark_ordered(db: Session, *, user_id: int, order_id: int) -> None:
    """标记访客已下单（转化成功）。"""
    today = _today_start()
    row = (
        db.query(VisitorInsight)
        .filter(
            VisitorInsight.user_id == user_id,
            VisitorInsight.visit_date >= today,
        )
        .first()
    )
    if row is None:
        return
    row.ordered = 1
    row.order_id = order_id
    row.primary_intent = "order"
    db.commit()


def get_daily_analytics(db: Session) -> dict[str, Any]:
    """聚合今日访客分析数据。"""
    today = _today_start()

    # 总访客数
    total_visitors = (
        db.query(func.count(VisitorInsight.insight_id))
        .filter(VisitorInsight.visit_date >= today)
        .scalar()
        or 0
    )

    # 下单访客
    ordered_visitors = (
        db.query(func.count(VisitorInsight.insight_id))
        .filter(
            VisitorInsight.visit_date >= today,
            VisitorInsight.ordered == 1,
        )
        .scalar()
        or 0
    )

    # 未下单访客（潜在流失）
    churned_visitors = total_visitors - ordered_visitors

    # 转化率
    conversion_rate = (ordered_visitors / total_visitors * 100) if total_visitors > 0 else 0.0

    # 意图分布
    intent_rows = (
        db.query(
            VisitorInsight.primary_intent,
            func.count(VisitorInsight.insight_id),
        )
        .filter(VisitorInsight.visit_date >= today)
        .group_by(VisitorInsight.primary_intent)
        .all()
    )
    intent_distribution = {
        intent: count for intent, count in intent_rows
    }

    # 访客列表（按消息数排序）
    visitors = (
        db.query(VisitorInsight)
        .filter(VisitorInsight.visit_date >= today)
        .order_by(VisitorInsight.message_count.desc(), VisitorInsight.visit_date.desc())
        .limit(30)
        .all()
    )
    visitor_list = [
        {
            "user_id": v.user_id,
            "first_message": v.first_message,
            "last_message": v.last_message,
            "message_count": v.message_count,
            "primary_intent": v.primary_intent,
            "ordered": v.ordered,
            "order_id": v.order_id,
            "churn_reason": v.churn_reason,
            "ai_insight": v.ai_insight,
            "visit_time": v.visit_date.strftime("%H:%M") if v.visit_date else "",
        }
        for v in visitors
    ]

    return {
        "total_visitors": total_visitors,
        "ordered_visitors": ordered_visitors,
        "churned_visitors": churned_visitors,
        "conversion_rate": round(conversion_rate, 1),
        "intent_distribution": intent_distribution,
        "visitors": visitor_list,
    }


def get_churn_analysis(db: Session) -> dict[str, Any]:
    """聚合流失原因分析（今日 + 全局模式）。"""
    today = _today_start()

    # 今日未下单访客（有流失原因的）
    churned_today = (
        db.query(VisitorInsight)
        .filter(
            VisitorInsight.visit_date >= today,
            VisitorInsight.ordered == 0,
        )
        .order_by(VisitorInsight.message_count.desc())
        .limit(20)
        .all()
    )

    churn_list = [
        {
            "user_id": v.user_id,
            "message_count": v.message_count,
            "primary_intent": v.primary_intent,
            "last_message": v.last_message,
            "churn_reason": v.churn_reason,
            "ai_insight": v.ai_insight,
        }
        for v in churned_today
    ]

    # 全局流失模式分类（最近30天）
    recent_churns = (
        db.query(VisitorInsight)
        .filter(
            VisitorInsight.ordered == 0,
            VisitorInsight.churn_reason.isnot(None),
            VisitorInsight.visit_date >= datetime.combine(
                date.today().replace(day=max(1, date.today().day - 30)),
                datetime.min.time(),
            ),
        )
        .all()
    )

    # 简单分类：按 churn_reason 关键词归类
    _CATEGORY_KEYWORDS = {
        "price": ["贵", "价格", "太贵", "便宜", "划算", "预算"],
        "taste": ["口味", "苦", "甜", "不喜欢", "不合", "不好喝", "难喝"],
        "variety": ["没有", "没找到", "不想", "品种", "选择"],
        "hesitation": ["再看看", "考虑", "下次", "等等", "不确定"],
        "experience": ["卡", "慢", "失败", "错误", "报错", "不方便"],
    }

    category_counts: dict[str, int] = {}
    for v in recent_churns:
        reason = (v.churn_reason or "").lower()
        categorized = False
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            if any(kw in reason for kw in keywords):
                category_counts[cat] = category_counts.get(cat, 0) + 1
                categorized = True
                break
        if not categorized:
            category_counts["other"] = category_counts.get("other", 0) + 1

    return {
        "today_churned": len(churned_today),
        "today_churn_details": churn_list,
        "churn_patterns": category_counts,
        "total_analyzed": len(recent_churns),
    }


# ============================================================
# LLM 流失分析（异步后台执行）
# ============================================================

_CHURN_ANALYSIS_PROMPT = (
    "你是咖啡馆经营分析师。根据以下访客的聊天记录摘要，分析该访客最终没有下单的可能原因。\n"
    "请用一句话给出最可能的流失原因（如「价格偏高」「未找到心仪口味」「只是浏览未决定购买」等）。\n\n"
    "访客信息：\n"
    "- 意图分类: {intent}\n"
    "- 消息数: {msg_count}\n"
    "- 首条消息: {first_msg}\n"
    "- 末条消息: {last_msg}\n\n"
    "请直接输出流失原因（15字以内），不要输出其他内容。"
)


def _analyze_single_churn(db: Session, visitor: VisitorInsight) -> str:
    """用 LLM 分析单个访客的流失原因。"""
    try:
        from app.llm import client as llm

        prompt = _CHURN_ANALYSIS_PROMPT.format(
            intent=visitor.primary_intent,
            msg_count=visitor.message_count,
            first_msg=visitor.first_message or "",
            last_msg=visitor.last_message or "",
        )
        reason = llm.chat([], prompt, "").strip()
        if len(reason) > 100:
            reason = reason[:100]
        return reason
    except Exception as exc:
        logger.warning("LLM 流失分析失败（用户 %s）: %s", visitor.user_id, exc)
        return ""


def _analyze_churn_batch(db: Session) -> int:
    """批量分析今日未下单且未分析过的访客。

    对每个访客：
      1. LLM 生成流失原因
      2. 通过 experience_agent 记录到自进化系统（MySQL + Redis + EvoMap）
    返回分析条数。
    """
    today = _today_start()
    visitors = (
        db.query(VisitorInsight)
        .filter(
            VisitorInsight.visit_date >= today,
            VisitorInsight.ordered == 0,
            VisitorInsight.churn_reason.is_(None),
            VisitorInsight.message_count >= 1,
        )
        .limit(5)  # 每次最多分析5个，避免长时间阻塞
        .all()
    )

    if not visitors:
        return 0

    analyzed = 0
    from app.services.agents import experience_agent

    for v in visitors:
        reason = _analyze_single_churn(db, v)
        if reason:
            v.churn_reason = reason
            db.commit()
            analyzed += 1
            # 通过自进化系统记录流失教训
            try:
                experience_agent.save_experience(
                    db,
                    user_id=v.user_id,
                    agent_role="analytics",
                    insight=f"访客流失原因: {reason} (意图: {v.primary_intent}, 消息数: {v.message_count})",
                    context_tags=f"churn,{v.primary_intent}",
                    rating=2,
                )
            except Exception as exc:
                logger.warning("流失经验记录失败: %s", exc)
        else:
            # LLM 没返回，标记为已分析避免重复
            v.churn_reason = "分析中..."
            db.commit()

    return analyzed


def analyze_churn_async() -> None:
    """异步触发流失分析（在新线程中执行，不阻塞 /chat 响应）。"""
    def _run():
        try:
            from app.db.database import SessionLocal
            db = SessionLocal()
            try:
                count = _analyze_churn_batch(db)
                if count > 0:
                    logger.info("流失分析完成: 分析了 %d 位访客", count)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("异步流失分析失败: %s", exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
