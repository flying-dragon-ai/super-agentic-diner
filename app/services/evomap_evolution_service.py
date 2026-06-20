"""EvoMap 群体进化 API 客户端：心跳 / 记忆读写 / 社区经验拉取。

职责：
  1. heartbeat()：定时心跳，保持节点在线 + 获取进化圈共享经验池（circle_experience）
  2. record_lesson()：把复盘 Agent(事后复盘) 的教训发布到 EvoMap 进化记忆
  3. recall_community_lessons()：检索社区同类经验（供推荐 Agent 融合）
  4. get_memory_status()：记忆系统状态（供大屏展示）

所有调用失败不阻塞主流程（仅记日志），因为本地 MySQL + Redis 是权威降级源。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings

logger = logging.getLogger(__name__)

_HUB = "https://evomap.ai"


def _is_configured() -> bool:
    """是否配置了 EvoMap 节点身份（node_id + node_secret）。"""
    return bool(settings.evomap_node_id and settings.evomap_node_secret)


def _post_json(url: str, body: dict[str, Any], *, auth: bool = True) -> dict[str, Any] | None:
    """POST JSON 到 EvoMap Hub，返回响应 dict；失败返回 None（不抛异常）。"""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {settings.evomap_node_secret}"
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=payload, method="POST", headers=headers)
    try:
        with urlopen(req, timeout=float(settings.evomap_request_timeout_seconds)) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.warning("EvoMap POST %s 失败: %s", url, exc)
        return None


def _get_json(url: str, *, auth: bool = True) -> dict[str, Any] | None:
    """GET JSON 从 EvoMap Hub；失败返回 None。"""
    headers = {"Accept": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {settings.evomap_node_secret}"
    req = Request(url, method="GET", headers=headers)
    try:
        with urlopen(req, timeout=float(settings.evomap_request_timeout_seconds)) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.warning("EvoMap GET %s 失败: %s", url, exc)
        return None


def _envelope(message_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """构造 GEP-A2A(进化协议) 标准信封。"""
    ms = int(time.time() * 1000)
    return {
        "protocol": "gep-a2a",
        "protocol_version": "1.0.0",
        "message_type": message_type,
        "message_id": f"msg_{ms}_{ms % 10000}",
        "sender_id": settings.evomap_node_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "payload": payload,
    }


# ============================================================
# 心跳：保持节点在线 + 获取进化圈共享经验池
# ============================================================

def heartbeat() -> dict[str, Any] | None:
    """发送心跳，返回 Hub 响应（含 circle_experience / credit_balance 等）。

    失败不抛异常，仅返回 None。
    """
    if not _is_configured():
        return None
    return _post_json(
        f"{_HUB}/a2a/heartbeat",
        {"node_id": settings.evomap_node_id},
    )


def get_node_status() -> dict[str, Any]:
    """获取节点状态摘要（供大屏 /admin/evomap/status 展示）。"""
    if not _is_configured():
        return {"configured": False, "node_id": "", "message": "未配置 EvoMap 节点身份"}
    resp = heartbeat()
    if not resp:
        return {"configured": True, "node_id": settings.evomap_node_id, "online": False, "message": "心跳失败"}
    circle = resp.get("circle_experience")
    novelty = resp.get("novelty")
    return {
        "configured": True,
        "node_id": settings.evomap_node_id,
        "online": True,
        "claimed": resp.get("claimed"),
        "credit_balance": resp.get("credit_balance"),
        "guild_id": settings.evomap_guild_id,
        "circle_id": circle.get("circle_id") if circle else None,
        "circle_member_count": circle.get("member_count") if circle else 0,
        "circle_signals": circle.get("signals_focus", []) if circle else [],
        "novelty_score": novelty.get("score") if novelty else None,
        "novelty_performance": novelty.get("performance") if novelty else None,
        "capability_gaps": resp.get("capability_gaps", []),
        "next_heartbeat_ms": resp.get("next_heartbeat_ms"),
    }


# ============================================================
# 进化记忆：发布教训 + 检索社区经验
# ============================================================

def record_lesson(
    *,
    insight: str,
    mistake_type: str | None = None,
    coffee_name: str | None = None,
    user_context: str | None = None,
    rating: int | None = None,
) -> dict[str, Any] | None:
    """把复盘 Agent 的教训发布到 EvoMap 进化记忆（POST /a2a/memory/record）。

    成功返回 Hub 响应；失败返回 None（不阻塞主流程）。
    """
    if not _is_configured():
        logger.debug("EvoMap 记忆发布跳过：未配置节点身份")
        return None
    payload = {
        "type": "lesson",
        "domain": "coffee_recommendation",
        "insight": insight,
        "metadata": {
            "mistake_type": mistake_type or "unknown",
            "coffee_name": coffee_name or "",
            "user_context": user_context or "",
            "rating": rating,
            "source": "coffee-ai-boss",
        },
    }
    body = _envelope("memory_record", payload)
    resp = _post_json(f"{_HUB}/a2a/memory/record", body)
    if resp:
        logger.info("EvoMap 记忆发布成功: %s", insight[:50])
    return resp


def recall_community_lessons(domain: str = "coffee_recommendation", limit: int = 10) -> list[dict[str, Any]]:
    """检索社区同类经验（POST /a2a/memory/recall），返回教训列表。

    失败返回空列表（推荐 Agent 照常工作，不依赖社区经验）。
    """
    if not _is_configured():
        return []
    payload = {
        "domain": domain,
        "limit": limit,
        "query": "coffee recommendation mistake lesson",
    }
    body = _envelope("memory_recall", payload)
    resp = _post_json(f"{_HUB}/a2a/memory/recall", body)
    if not resp:
        return []
    # 从 payload 提取教训列表（格式兼容多种可能）
    lessons = resp.get("payload", {}).get("lessons") or resp.get("lessons") or resp.get("payload", {}).get("results") or []
    return lessons if isinstance(lessons, list) else []


def get_memory_status() -> dict[str, Any] | None:
    """获取记忆系统状态（GET /a2a/memory/status）。"""
    if not _is_configured():
        return None
    return _get_json(f"{_HUB}/a2a/memory/status")


# ============================================================
# 进化圈共享经验池（从心跳响应中提取）
# ============================================================

def fetch_circle_experience() -> list[dict[str, Any]]:
    """发送心跳并提取进化圈共享经验池（lessons + execution_traces）。

    供定时任务调用，拉取后缓存到 Redis 供推荐 Agent 快速读取。
    """
    resp = heartbeat()
    if not resp:
        return []
    circle = resp.get("circle_experience")
    if not circle:
        return []
    lessons = circle.get("lessons", [])
    return lessons if isinstance(lessons, list) else []
