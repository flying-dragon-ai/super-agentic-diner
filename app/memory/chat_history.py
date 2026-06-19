"""Short-term chat memory and pending-order storage."""
from __future__ import annotations

import json

import redis

from app.config import settings


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


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
    """
    r = _client()
    key = _key(user_id)
    r.lpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
    keep = settings.chat_history_rounds * 2  # 5轮 × 每轮2条 = 保留10条
    r.ltrim(key, 0, keep - 1)                # 裁剪：只留前10条
    r.expire(key, settings.chat_history_ttl)  # 30分钟后自动过期


def get_history(user_id: int) -> list[dict]:
    """【任务一·Redis】读取用户最近 5 轮对话历史

    LRANGE 取全部后 reversed 转为时间正序（最早的在前），
    直接传给 LLM 作为对话上下文，让 AI "记住刚才聊了什么"。
    """
    r = _client()
    raw = r.lrange(_key(user_id), 0, -1)  # LPUSH 后最新在前
    return [json.loads(x) for x in reversed(raw)]  # 反转为时间正序（最早→最新）


def clear_history(user_id: int) -> None:
    _client().delete(_key(user_id))


# ============================================================
# 【任务三·Redis】待确认订单（两段式下单：先确认、再扣款）
# 用 String 类型存储 JSON，key 格式：chat:pending:{user_id}
# 用户说"下单"→先存摘要→显示确认提示→用户回复"确认"→才执行扣款
# ============================================================

_PENDING_KEY = "chat:pending:{}"  # .format(user_id)


def set_pending_order(user_id: int, data: dict) -> None:
    """存储待确认的订单（JSON），等用户回复「确认」后执行扣款"""
    r = _client()
    r.set(_PENDING_KEY.format(user_id), json.dumps(data, ensure_ascii=False))
    r.expire(_PENDING_KEY.format(user_id), settings.chat_history_ttl)


def get_pending_order(user_id: int) -> dict | None:
    """读取待确认订单，无则返回 None"""
    raw = _client().get(_PENDING_KEY.format(user_id))
    if raw:
        return json.loads(raw)
    return None


def clear_pending_order(user_id: int) -> None:
    _client().delete(_PENDING_KEY.format(user_id))
