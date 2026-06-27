"""用户画像服务：基于聊天+订单历史归纳口味偏好，供推荐 Agent 软引导。

触发：仅在订单支付完成后调 summarize_async(user_id)（web + skill 两处）。
分析对象：仅登录用户（有 UserAccount），匿名 user_id 跳过，避免污染。
总结策略：增量——用 last_msg_id 游标只处理上次总结之后的新对话，与旧画像累积融合。
LLM 失败/无 key：保留旧画像不覆盖，best-effort。
存储：写 user_profile 表 + 同步 summary 到 User.taste_preference（前端 /user 零改动可见）。
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ChatMessage, Order, User, UserAccount, UserProfile
from app.llm import client as llm
from app.memory._redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Redis 锁 key：防止「购买完成」短时间内重复触发同一用户的画像总结（如多次下单）。
# 锁时效较短（30 分钟），既防重入又允许稍后随新对话重新总结。
_PROFILE_LOCK_TTL_SECONDS = 1800
_PROFILE_LOCK_KEY = "profile:lock:{}"

# 增量总结：单次最多处理的新对话条数上限（防止历史积压时 prompt 过长 + LLM 超时）。
_MAX_NEW_MESSAGES = 40
# 单次纳入 LLM 分析的最近订单数（咖啡名/金额/品类，口味与价格画像依据）。
_MAX_RECENT_ORDERS = 10
# 画像摘要镜像写入 User.taste_preference 时的截断长度（字段是 String(255)）。
_SUMMARY_MIRROR_LIMIT = 200


def _redis():
    return get_redis_client()


def _is_logged_in_user(db: Session, user_id: int) -> bool:
    """是否登录用户（有 UserAccount）。仅对登录用户做画像，过滤匿名 web user_id。"""
    return db.query(UserAccount.user_id).filter(UserAccount.user_id == user_id).first() is not None


def _fetch_new_messages(db: Session, user_id: int, since_msg_id: int) -> list[ChatMessage]:
    """拉取 since_msg_id 之后的新对话（时间正序），最多 _MAX_NEW_MESSAGES 条。"""
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.message_id > since_msg_id)
        .order_by(ChatMessage.message_id.asc())
        .limit(_MAX_NEW_MESSAGES)
        .all()
    )


def _fetch_recent_orders(db: Session, user_id: int) -> list[Order]:
    """拉取最近 _MAX_RECENT_ORDERS 单已支付订单（口味/价格/品类画像依据）。"""
    return (
        db.query(Order)
        .filter(Order.user_id == user_id, Order.payment_status == "paid")
        .order_by(Order.created_at.desc())
        .limit(_MAX_RECENT_ORDERS)
        .all()
    )


def _build_llm_input(
    new_messages: list[ChatMessage],
    recent_orders: list[Order],
    old_summary: str | None,
) -> str:
    """把新对话 + 最近订单 + 旧画像摘要拼成 LLM 的 context 输入。"""
    parts: list[str] = []

    # 新对话（若为空，本次总结无新信息）
    if new_messages:
        chat_lines = [f"{m.role}: {m.content}" for m in new_messages]
        parts.append("【本次新增对话】\n" + "\n".join(chat_lines))
    else:
        parts.append("【本次新增对话】（无）")

    # 最近订单（咖啡名 + 金额）
    if recent_orders:
        order_lines = [f"- {o.coffee_name}（¥{o.amount}）" for o in recent_orders]
        parts.append("【最近订单】\n" + "\n".join(order_lines))
    else:
        parts.append("【最近订单】（无）")

    # 旧画像（累积融合，不丢历史）
    if old_summary:
        parts.append(f"【旧画像摘要】\n{old_summary}")
    else:
        parts.append("【旧画像摘要】（首次画像）")

    return "\n\n".join(parts)


def _persist_profile(
    db: Session,
    user_id: int,
    profile_row: UserProfile | None,
    result: dict[str, Any],
    new_last_msg_id: int,
    order_count: int,
) -> None:
    """把 LLM 归纳结果写入 user_profile（upsert）+ 镜像 summary 到 User.taste_preference。"""
    summary = (result.get("summary") or "").strip()[:200]
    profile_json = json.dumps(result, ensure_ascii=False)

    if profile_row is None:
        profile_row = UserProfile(user_id=user_id)
        db.add(profile_row)

    profile_row.summary = summary or None
    profile_row.profile_json = profile_json
    profile_row.last_msg_id = new_last_msg_id
    profile_row.order_count = order_count
    profile_row.updated_at = datetime.utcnow()

    # 镜像写入 User.taste_preference，让 /user 端点零改动可见
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is not None:
        user.taste_preference = (summary or "")[:_SUMMARY_MIRROR_LIMIT] or None
        user.updated_at = datetime.utcnow()

    db.commit()


def summarize_user_session(db: Session, user_id: int) -> dict | None:
    """对一个用户做一次增量画像总结。

    流程：
      1. 仅登录用户校验（匿名跳过）
      2. 读取现有 user_profile（含 last_msg_id 游标 + 旧 summary）
      3. 拉取自 last_msg_id 之后的新对话；若没有新对话则跳过（无需重算）
      4. 拉取最近订单 + 拼装 LLM 输入
      5. LLM 归纳（无 key/超时/解析失败 → 保留旧画像，返回 None）
      6. 写 user_profile（upsert）+ 镜像 User.taste_preference
      7. 推进 last_msg_id 游标

    返回归纳后的画像 dict（含 summary 等），失败返回 None。
    """
    # 1. 仅登录用户
    if not _is_logged_in_user(db, user_id):
        logger.info("画像总结跳过：user_id=%s 非登录用户", user_id)
        return None

    # 2. 读取现有画像（游标 + 旧摘要）
    profile_row = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    old_summary = profile_row.summary if profile_row else None
    since_msg_id = profile_row.last_msg_id if profile_row else 0

    # 3. 拉取新对话；无新对话则跳过（避免无意义重算）
    new_messages = _fetch_new_messages(db, user_id, since_msg_id)
    if not new_messages:
        logger.info("画像总结跳过：user_id=%s 无新对话（last_msg_id=%s）", user_id, since_msg_id)
        return None

    # 4. 拉取最近订单 + 拼装 LLM 输入
    recent_orders = _fetch_recent_orders(db, user_id)
    context = _build_llm_input(new_messages, recent_orders, old_summary)

    # 5. LLM 归纳
    if not llm.has_real_key():
        logger.info("画像总结跳过：无 LLM key，保留旧画像（user_id=%s）", user_id)
        return None
    raw = llm.chat_with_role(
        system_prompt=llm.USER_PROFILE_PROMPT,
        context=context,
        history=[],
        user_msg="请归纳这位顾客的画像。",
        timeout_seconds=settings.llm_review_timeout_seconds,
    )
    result = llm.parse_json_response(raw)
    if not result or "summary" not in result:
        logger.warning("画像 LLM 输出解析失败 user_id=%s: %s", user_id, (raw or "")[:120])
        return None

    # 6. 持久化 + 镜像
    new_last_msg_id = new_messages[-1].message_id  # 最后一条新消息的 id 推进游标
    _persist_profile(db, user_id, profile_row, result, new_last_msg_id, len(recent_orders))

    logger.info("画像总结完成 user_id=%s summary=%s", user_id, (result.get("summary") or "")[:60])
    return result


def summarize_async(user_id: int) -> None:
    """异步触发画像总结（fire-and-forget 线程，不阻塞下单/聊天响应）。

    - 独立 SessionLocal，不污染调用方的 session；
    - Redis 锁防短时间内重复触发（如连续下单）；
    - 全程 try/except swallow：画像分析绝不阻断订单/支付业务（项目铁律）。
    """
    # Redis 锁：已锁则直接返回，不重复跑
    try:
        r = _redis()
        if r.set(_PROFILE_LOCK_KEY.format(user_id), "1", ex=_PROFILE_LOCK_TTL_SECONDS, nx=True):
            locked = True
        else:
            locked = False
    except Exception:
        # Redis 不可用时降级为不锁（允许重复跑，靠 try/except 兜底）
        locked = True

    if not locked:
        logger.info("画像总结跳过：user_id=%s 锁存在（近期已触发）", user_id)
        return

    def _run():
        try:
            from app.db.database import SessionLocal

            db = SessionLocal()
            try:
                summarize_user_session(db, user_id)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("异步画像总结失败 user_id=%s: %s", user_id, exc, exc_info=True)

    threading.Thread(target=_run, daemon=True).start()


def get_profile_summary(user_id: int, db: Session | None = None) -> str:
    """读取用户画像摘要文本（供推荐 Agent 软引导）。

    返回 summary 文本；无画像返回空字符串。db 可选：传入则复用，不传则开独立 session。
    """
    owns_session = db is None
    if owns_session:
        from app.db.database import SessionLocal

        db = SessionLocal()
    try:
        row = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        return (row.summary or "") if row else ""
    except Exception:
        logger.warning("读取画像摘要失败 user_id=%s", user_id, exc_info=True)
        return ""
    finally:
        if owns_session:
            db.close()
