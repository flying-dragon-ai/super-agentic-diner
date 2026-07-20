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

from redis.exceptions import RedisError, ResponseError

from app.config import settings
from app.memory._redis_client import get_redis_client

logger = logging.getLogger(__name__)


def _client():
    return get_redis_client()


def _key(user_id: int | str) -> str:
    """【任务一·Redis】每个用户的对话历史用一个独立的 List 存储
    key 格式：chat:history:{user_id}，如 chat:history:1
    """
    return f"chat:history:{user_id}"


def add_message(user_id: int | str, role: str, content: str) -> None:
    """【任务一·Redis】写入一条消息到 Redis List

    三步操作（原子性由 Redis 单线程保证）：
    1. LPUSH：把新消息插到列表头部（最新在前）
    2. LTRIM：裁剪列表，只保留最近 5 轮（5轮×2条=10条），实现滑动窗口
    3. EXPIRE：重置 30 分钟过期时间，实现短期记忆（无活动即遗忘）

    同时【画像功能】把消息持久化到 SQL(chat_message 表)，作为长期画像的数据源。
    Redis 与 SQL 都是 best-effort 降级：任一失败都记 warning 后吞掉异常，
    不阻断下单/聊天主流程。SQL 写入用独立 SessionLocal，不污染调用方的 session。
    """
    # 1. 写 Redis（短期记忆，供推荐/复盘快速读取）
    try:
        r = _client()
        key = _key(user_id)
        keep = settings.chat_history_rounds * 2  # 5轮 × 每轮2条 = 保留10条
        payload = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        if hasattr(r, "pipeline"):
            with r.pipeline(transaction=True) as pipe:
                pipe.lpush(key, payload)
                pipe.ltrim(key, 0, keep - 1)  # 裁剪：只留前10条
                pipe.expire(key, settings.chat_history_ttl)  # 30分钟后自动过期
                pipe.execute()
        else:  # Lightweight test doubles; real Redis clients always use pipeline.
            r.lpush(key, payload)
            r.ltrim(key, 0, keep - 1)
            r.expire(key, settings.chat_history_ttl)
    except RedisError:
        # 对话历史写不进不影响下单/支付；Redis 恢复后自愈。
        logger.warning(
            "Redis 写对话历史失败（已降级）user_id=%s role=%s", user_id, role, exc_info=True
        )

    # 2. 写 SQL（长期归档，供用户画像增量总结）
    # Anonymous chat identities are represented by non-positive IDs and remain
    # Redis-only. This prevents FK-orphaned SQL archive rows while preserving
    # short-term conversation memory for guests.
    if not isinstance(user_id, int) or user_id <= 0:
        return

    try:
        from app.db.database import SessionLocal
        from app.db.models import ChatMessage

        db = SessionLocal()
        try:
            db.add(ChatMessage(user_id=user_id, role=role, content=content))
            db.commit()
        finally:
            db.close()
    except Exception:
        # 持久化失败不影响聊天；画像下次触发时这条消息可能漏，但不阻断业务。
        logger.warning(
            "SQL 写对话归档失败（已降级）user_id=%s role=%s", user_id, role, exc_info=True
        )


def get_history(user_id: int | str) -> list[dict]:
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


def clear_history(user_id: int | str) -> None:
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


def set_pending_order(user_id: int | str, data: dict) -> None:
    """存储待确认的订单（JSON），等用户回复「确认」后执行扣款

    Redis 不可用时 best-effort 吞掉异常：调用方随后在 get_pending_order
    拿不到时按"无待确认订单"重新走下单流程，不会 500。
    """
    try:
        r = _client()
        key = _PENDING_KEY.format(user_id)
        payload = json.dumps(data, ensure_ascii=False)
        try:
            r.set(key, payload, ex=settings.chat_history_ttl)
        except TypeError:  # Lightweight test doubles without SET options.
            r.set(key, payload)
            r.expire(key, settings.chat_history_ttl)
    except RedisError:
        logger.warning("Redis 写待确认订单失败（已降级）user_id=%s", user_id, exc_info=True)


def get_pending_order(user_id: int | str) -> dict | None:
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


def claim_pending_order(user_id: int | str) -> dict | None:
    """Atomically fetch and remove a pending order for confirmation.

    Concurrent confirmation requests can no longer both observe the same JSON
    and charge twice. ``GETDEL`` is used when available; the Lua fallback keeps
    the same atomic semantics on older Redis-compatible servers.
    """
    key = _PENDING_KEY.format(user_id)
    try:
        r = _client()
        try:
            raw = r.getdel(key)
        except (AttributeError, NotImplementedError, ResponseError):
            raw = r.eval(
                "local v=redis.call('GET',KEYS[1]); "
                "if v then redis.call('DEL',KEYS[1]); end; return v",
                1,
                key,
            )
    except RedisError:
        logger.warning(
            "Redis 原子领取待确认订单失败（已降级为无）user_id=%s",
            user_id,
            exc_info=True,
        )
        return None

    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("丢弃损坏的已领取订单 user_id=%s: %r", user_id, raw[:80])
        return None


def migrate_pending_order(source_user_id: int | str, target_user_id: int | str) -> bool:
    """Atomically move a guest checkout to an authenticated account.

    ``RENAMENX`` preserves the source TTL and refuses to overwrite an existing
    account checkout. This avoids the loss window in a GETDEL + SET sequence if
    Redis becomes unavailable between the two commands.
    """
    if source_user_id == target_user_id:
        return False
    source_key = _PENDING_KEY.format(source_user_id)
    target_key = _PENDING_KEY.format(target_user_id)
    try:
        return bool(_client().renamenx(source_key, target_key))
    except ResponseError as exc:
        # Redis reports a missing source as a command error rather than false.
        if "no such key" in str(exc).lower():
            return False
        logger.warning(
            "Redis 原子迁移待确认订单失败 source=%s target=%s",
            source_user_id,
            target_user_id,
            exc_info=True,
        )
        return False
    except (AttributeError, NotImplementedError, RedisError):
        logger.warning(
            "Redis 原子迁移待确认订单失败 source=%s target=%s",
            source_user_id,
            target_user_id,
            exc_info=True,
        )
        return False


def clear_pending_order(user_id: int | str) -> None:
    try:
        _client().delete(_PENDING_KEY.format(user_id))
    except RedisError:
        logger.warning("Redis 清除待确认订单失败（已降级）user_id=%s", user_id, exc_info=True)
