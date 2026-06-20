"""经验继承 Agent(经验积累)：MySQL + Redis + EvoMap 三写。

职责：
  1. save_experience()：复盘 Agent 分析出教训后，三写 MySQL + Redis + EvoMap(群体进化)
  2. get_experience_for_user()：推荐 Agent 调用前读取，合并本地经验 + 社区缓存经验
  3. sync_community_experience()：定时任务调，从 EvoMap 拉取社区经验缓存到 Redis

Redis key 格式：
  agent:experience:{user_id}（List，LPUSH 写入，LTRIM 保留最近 20 条）— 本地教训
  agent:community_experience（List，LPUSH + LTRIM 20 条）— 社区经验缓存
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime

import redis
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AgentExperience

logger = logging.getLogger(__name__)

_REDIS_KEY = "agent:experience:{}"
_REDIS_COMMUNITY_KEY = "agent:community_experience"
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
    """三写经验：MySQL（持久审计）+ Redis（快速读取）+ EvoMap（群体进化共享）。

    MySQL 是权威源；Redis 和 EvoMap 写失败不阻塞主流程。
    """
    # 1. 写 MySQL（权威源）
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

    # 3. 写 EvoMap（群体进化共享，全平台受益）
    try:
        from app.services import evomap_evolution_service
        evomap_evolution_service.record_lesson(
            insight=insight,
            mistake_type=context_tags,
            coffee_name=coffee_name,
            user_context=context_tags,
            rating=rating,
        )
    except Exception as exc:
        logger.warning("经验写入 EvoMap(群体进化) 失败（本地已写成功，不阻塞）: %s", exc)

    return row


def get_experience_for_user(user_id: int) -> str:
    """读取该用户的经验提示，合并本地经验 + 社区经验（供推荐 Agent 融合）。

    返回拼接好的「推荐前必读」文本，格式：
      《本地经验》
      • 本地教训1
      • 本地教训2
      《社区经验》
      • 社区教训1
    无经验返回空字符串。
    """
    parts: list[str] = []

    # 读本地经验
    local_hints = _read_local_hints(user_id)
    if local_hints:
        parts.append("《本地经验》")
        parts.extend(f"• {h}" for h in local_hints)

    # 读社区经验（从 Redis 缓存读，由定时任务从 EvoMap 拉取）
    community_hints = _read_community_hints()
    if community_hints:
        parts.append("《社区经验》")
        parts.extend(f"• {h}" for h in community_hints)

    return "\n".join(parts) if parts else ""


# ============================================================
# 硬过滤：从经验中提取结构化过滤规则，推荐前直接剔除已知错项
# ============================================================

# 口味/品类关键词 → 对应的 product tags 匹配规则
# 当经验文本出现"不要X"/"不X"/"避开X"时，X 映射到这些 tag
_TAG_SYNONYMS: dict[str, list[str]] = {
    "甜": ["甜", "焦糖"],
    "苦": ["苦"],
    "牛奶": ["牛奶"],
    "奶": ["牛奶", "拿铁"],
    "拿铁": ["拿铁"],
    "美式": ["美式"],
    "摩卡": ["摩卡"],
    "焦糖": ["焦糖"],
    "椰香": ["椰香"],
    "果香": ["果香"],
    "冷萃": ["冷萃"],
    "酸": ["酸"],
}

# 否定前缀模式：经验文本中"不要X"/"不X"/"别X"→ X 是要避开的
_NEGATION_PATTERN = re.compile(
    r"(?:不要|不|别|避免|避开|去掉|没有|无|不适合|讨厌|反感)"
    r"(甜|苦|牛奶|奶|拿铁|美式|摩卡|焦糖|椰香|果香|冷萃|酸)"
)


def _extract_banned_tags(text: str) -> set[str]:
    """从经验文本中提取要避开的 tag（如"不要甜"→ {"甜", "焦糖"}）。

    用正则匹配"否定词+口味词"模式，再展开为同义词 tag 集合。
    """
    tags: set[str] = set()
    if not text:
        return tags
    for match in _NEGATION_PATTERN.finditer(text):
        keyword = match.group(1)
        # 展开同义词：如"奶"→ ["牛奶", "拿铁"]
        for tag in _TAG_SYNONYMS.get(keyword, [keyword]):
            tags.add(tag)
    return tags


def get_hard_filters(user_id: int) -> dict:
    """返回该用户的硬过滤规则，供推荐 Agent 在 RAG 检索后直接剔除。

    返回：
        {
            "banned_names": ["焦糖玛奇朵"],       # 按名字直接拉黑（曾推荐错的）
            "banned_tags": ["甜", "焦糖", "牛奶"], # 按标签过滤（用户明确不要的口味）
        }

    规则来源（从 Redis 本地经验提取）：
      1. coffee_name + rating ≤ 3 → 直接拉黑该咖啡名
      2. insight + tags 文本解析 → 提取否定口味 → 展开 tag 过滤
    """
    banned_names: set[str] = set()
    banned_tags: set[str] = set()

    try:
        r = _client()
        key = _REDIS_KEY.format(user_id)
        items = r.lrange(key, 0, -1)
        for raw in items:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            # 规则1：低评分的错推咖啡 → 拉黑名字
            rating = data.get("rating")
            coffee_name = data.get("coffee_name", "")
            if coffee_name and (rating is None or rating <= 3):
                banned_names.add(coffee_name)

            # 规则2：从 insight + tags 文本提取否定口味
            insight = data.get("insight", "")
            tags_text = data.get("tags", "")
            combined_text = f"{insight} {tags_text}"
            banned_tags.update(_extract_banned_tags(combined_text))
    except Exception as exc:
        logger.warning("硬过滤规则提取失败: %s", exc)

    return {
        "banned_names": list(banned_names),
        "banned_tags": list(banned_tags),
    }


def _read_local_hints(user_id: int) -> list[str]:
    """从 Redis 读取本地教训提示。"""
    try:
        r = _client()
        key = _REDIS_KEY.format(user_id)
        items = r.lrange(key, 0, -1)
        hints: list[str] = []
        for raw in items:
            try:
                data = json.loads(raw)
                hint = data.get("insight", "")
                if hint:
                    hints.append(hint)
            except (json.JSONDecodeError, TypeError):
                continue
        return hints
    except Exception:
        return []


def _read_community_hints() -> list[str]:
    """从 Redis 读取社区经验缓存（由 sync_community_experience 写入）。"""
    try:
        r = _client()
        items = r.lrange(_REDIS_COMMUNITY_KEY, 0, -1)
        hints: list[str] = []
        for raw in items:
            try:
                data = json.loads(raw)
                hint = data.get("insight", "")
                if hint:
                    hints.append(hint)
            except (json.JSONDecodeError, TypeError):
                continue
        return hints
    except Exception:
        return []


def sync_community_experience() -> int:
    """从 EvoMap 拉取社区经验，缓存到 Redis。供定时任务调用。

    返回拉取的经验条数。
    """
    try:
        from app.services import evomap_evolution_service
        lessons = evomap_evolution_service.fetch_circle_experience()
        if not lessons:
            return 0
        r = _client()
        # 清空旧缓存，写入新经验
        r.delete(_REDIS_COMMUNITY_KEY)
        for lesson in lessons[:_REDIS_MAX]:
            insight = ""
            if isinstance(lesson, dict):
                insight = lesson.get("insight") or lesson.get("lesson") or lesson.get("summary") or ""
            if insight:
                payload = json.dumps(
                    {"insight": str(insight)[:200], "source": "evomap_community"},
                    ensure_ascii=False,
                )
                r.rpush(_REDIS_COMMUNITY_KEY, payload)
        r.expire(_REDIS_COMMUNITY_KEY, 600)  # 10 分钟过期
        return len(lessons)
    except Exception as exc:
        logger.warning("社区经验同步失败: %s", exc)
        return 0


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
