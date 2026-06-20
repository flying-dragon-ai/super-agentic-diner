"""Short-term chat memory and pending-order storage.

All Redis access is wrapped so a flaky/unreachable Redis degrades gracefully
instead of crashing ``/chat`` with a 500:

* reads return an empty state (``get_history`` → ``[]``, ``get_pending_order``
  → ``None``) — the conversation / ordering flow continues without memory;
* writes are best-effort — a failure is logged and swallowed so the main
  business path (placing / confirming orders) is never blocked by Redis.

The client also pins short socket timeouts (``settings.redis_socket_*``) so a
dead connection fails in seconds rather than hanging for ~a minute.
"""
from __future__ import annotations

import json
import logging

import redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)


def _client() -> redis.Redis:
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
        socket_timeout=settings.redis_socket_timeout,
    )


def _key(user_id: int) -> str:
    """【任务一·Redis】每个用户的对话历史用一个独立的 List 存储
    key 格式：chat:history:{user_id}，如 chat:history:1
    """
    return f"chat:history:{user_id}"


def add_message(user_id: int, role: str, content: str) -> None:
    """【任务一·Redis】写入一条消息到 Redis List

    三步操作（原子性由 Redis 单线程保证）：
    1. LPUSH：把新消息插到列表头部（最新在前）
    2. LTRIM：裁剪列表，只保留最近 5 轮（5轮×2条=10条），实现滑动窗口
    3. EXPIRE：重置 30 分钟过期时间，实现短期记忆（无活动即遗忘）

    Redis 不可用时 best-effort 降级：记 warning 后吞掉异常，不阻断下单主流程。
    """
    try:
        r = _client()
        key = _key(user_id)
        r.lpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
        keep = settings.chat_history_rounds * 2  # 5轮 × 每轮2条 = 保留10条
        r.ltrim(key, 0, keep - 1)                # 裁剪：只留前10条
        r.expire(key, settings.chat_history_ttl)  # 30分钟后自动过期
    except RedisError:
        # 对话历史写不进不影响下单/支付；Redis 恢复后自愈。
        logger.warning(
            "Redis 写对话历史失败（已降级）user_id=%s role=%s", user_id, role, exc_info=True
        )


def get_history(user_id: int) -> list[dict]:
    """【任务一·Redis】读取用户最近 5 轮对话历史

    LRANGE 取全部后 reversed 转为时间正序（最早的在前），
    直接传给 LLM 作为对话上下文，让 AI "记住刚才聊了什么"。

    Redis 不可用时降级返回空列表：对话照常进行，只是没有历史记忆。
    """
    try:
        r = _client()
        raw = r.lrange(_key(user_id), 0, -1)  # LPUSH 后最新在前
    except RedisError:
        logger.warning("Redis 读对话历史失败（已降级为空）user_id=%s", user_id, exc_info=True)
        return []
    messages: list[dict] = []
    for item in reversed(raw):  # 反转为时间正序（最早→最新）
        try:
            messages.append(json.loads(item))
        except (json.JSONDecodeError, TypeError):
            # 单条脏数据不应让整个 /chat 瘫痪：跳过并告警
            logger.warning("跳过损坏的对话历史条目 user_id=%s: %r", user_id, item[:80])
    return messages


def clear_history(user_id: int) -> None:
    try:
        _client().delete(_key(user_id))
    except RedisError:
        logger.warning("Redis 清空对话历史失败（已降级）user_id=%s", user_id, exc_info=True)


# ============================================================
# 【任务三·Redis】待确认订单（两段式下单：先确认、再扣款）
# 用 String 类型存储 JSON，key 格式：chat:pending:{user_id}
# 用户说"下单"→先存摘要→显示确认提示→用户回复"确认"→才执行扣款
# ============================================================

_PENDING_KEY = "chat:pending:{}"  # .format(user_id)


def set_pending_order(user_id: int, data: dict) -> None:
    """存储待确认的订单（JSON），等用户回复「确认」后执行扣款

    Redis 不可用时 best-effort 吞掉异常：调用方随后在 get_pending_order
    拿不到时按"无待确认订单"重新走下单流程，不会 500。
    """
    try:
        r = _client()
        r.set(_PENDING_KEY.format(user_id), json.dumps(data, ensure_ascii=False))
        r.expire(_PENDING_KEY.format(user_id), settings.chat_history_ttl)
    except RedisError:
        logger.warning("Redis 写待确认订单失败（已降级）user_id=%s", user_id, exc_info=True)


def get_pending_order(user_id: int) -> dict | None:
    """读取待确认订单，无则返回 None。损坏的 JSON 会被丢弃并清理，避免反复报错。

    Redis 不可用时降级返回 None：按"无待确认订单"处理，正常下单流程继续。
    """
    try:
        r = _client()
        key = _PENDING_KEY.format(user_id)
        raw = r.get(key)
    except RedisError:
        logger.warning("Redis 读待确认订单失败（已降级为无）user_id=%s", user_id, exc_info=True)
        return None
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # 脏数据直接清掉，下次让用户重新下单，而不是反复抛错
            logger.warning("丢弃损坏的待确认订单 user_id=%s: %r", user_id, raw[:80])
            try:
                r.delete(key)
            except RedisError:
                logger.warning(
                    "Redis 清理损坏待确认订单失败 user_id=%s", user_id, exc_info=True
                )
    return None


def clear_pending_order(user_id: int) -> None:
    try:
        _client().delete(_PENDING_KEY.format(user_id))
    except RedisError:
        logger.warning("Redis 清除待确认订单失败（已降级）user_id=%s", user_id, exc_info=True)
