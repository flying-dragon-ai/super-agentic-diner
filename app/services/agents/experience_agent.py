"""经验继承 Agent(经验积累)：MySQL 持久化 + Redis 快速读取双写。

职责：
  1. save_experience()：复盘 Agent(事后复盘) 分析出教训后，双写 MySQL + Redis
  2. get_experience_for_user()：推荐 Agent(推荐) 调用前读取，提供「推荐前必读」提示

Redis key 格式：agent:experience:{user_id}（List，LPUSH 写入，LTRIM 保留最近 20 条）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import redis
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AgentExperience

logger = logging.getLogger(__name__)

_REDIS_KEY = "agent:experience:{}"
_REDIS_MAX = 20


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def save_experience(
    db: Session,
    *,
    user_id: int,
    agent_role: str,
    insight: str,
    coffee_name: str | None = None,
    context_tags: str | None = None,
    rating: int | None = None,
    order_id: int | None = None,
    correlation_id: str | None = None,
) -> AgentExperience | None:
    """双写经验：先写 MySQL（持久审计），再写 Redis（快速读取）。

    MySQL 是权威源；Redis 写失败不阻塞主流程（仅记日志），因为推荐 Agent 下次
    仍可从 MySQL 回填。
    """
    # 1. 写 MySQL
    row = AgentExperience(
        user_id=user_id,
        agent_role=agent_role,
        coffee_name=coffee_name,
        context_tags=context_tags,
        insight=insight,
        rating=rating,
        order_id=order_id,
        correlation_id=correlation_id,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # 2. 写 Redis（快速读取，LPUSH + LTRIM 滑动窗口）
    try:
        r = _client()
        key = _REDIS_KEY.format(user_id)
        payload = json.dumps(
            {
                "insight": insight,
                "coffee_name": coffee_name,
                "tags": context_tags,
                "rating": rating,
                "role": agent_role,
            },
            ensure_ascii=False,
        )
        r.lpush(key, payload)
        r.ltrim(key, 0, _REDIS_MAX - 1)
    except Exception as exc:
        logger.warning("经验写入 Redis(缓存) 失败（MySQL 已写成功，不阻塞）: %s", exc)

    return row


def get_experience_for_user(user_id: int) -> str:
    """读取该用户的经验提示（供推荐 Agent 融合到上下文）。

    优先读 Redis（快）；Redis 空或异常时返回空字符串（推荐 Agent 照常工作）。
    """
    try:
        r = _client()
        key = _REDIS_KEY.format(user_id)
        items = r.lrange(key, 0, -1)
        if not items:
            return ""
        hints: list[str] = []
        for raw in items:
            try:
                data = json.loads(raw)
                hint = data.get("insight", "")
                if hint:
                    hints.append(hint)
            except (json.JSONDecodeError, TypeError):
                continue
        return "\n".join(f"• {h}" for h in hints) if hints else ""
    except Exception:
        return ""


def list_recent_experiences(db: Session, limit: int = 20) -> list[dict]:
    """列出最近的经验记录（供大屏 /admin/agent-collaboration 展示）。"""
    rows = (
        db.query(AgentExperience)
        .order_by(AgentExperience.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "experience_id": row.experience_id,
            "user_id": row.user_id,
            "agent_role": row.agent_role,
            "coffee_name": row.coffee_name,
            "context_tags": row.context_tags,
            "insight": row.insight,
            "rating": row.rating,
            "order_id": row.order_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
