"""复购意图识别 + 历史订单解析服务。

当用户说「和之前一样」「老样子」「上次那杯」等指代式复购意图时，
系统原本只看 Redis 对话历史盲猜（可能误判为刚才推荐的同款）。
本服务转而查询该用户的真实历史订单，按频次取最常点的那杯，
让复购落到用户真实偏好上，而非临时对话上下文。

接入点：main.py order 决策树第 3.4 路（对话历史盲扫）之前。
"""
from __future__ import annotations

import logging
from collections import Counter

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Order
from app.services.user_profile_service import get_profile_summary as _get_profile_summary

logger = logging.getLogger(__name__)

# 复购触发短语：用户用这些话表达「再来一杯我以前点过的」。
# 用子串匹配（in），所以「和之前一样」也能命中「还是来个和之前一样的吧」。
_REORDER_WORDS = (
    "和之前一样",
    "跟之前一样",
    "和上次一样",
    "跟上次一样",
    "上次那杯",
    "上次那个",
    "老样子",
    "常点的",
    "常喝的",
    "常点的那款",
    "我常",
    "跟刚才一样",  # 刚买完想再来一杯同款
    "再来一杯",  # "再来一杯刚才的"
    "再来一杯一样",
)

# 否定/修改信号：出现即视为「不是复购」（如「换一杯」「和之前不一样」）。
# 优先级高于 _REORDER_WORDS，避免「和之前不一样」被「和之前一样」子串误命中。
_REORDER_NEGATION_WORDS = (
    "不",
    "别",
    "换",
    "改",
    "取消",
    "退",
    "另外",
    "别的",
)


def detect_reorder_intent(user_msg: str) -> bool:
    """检测用户消息是否表达「复购以前点过的」意图。

    判定条件（同时满足）：
      1. 消息含复购触发短语（如「和之前一样」「老样子」）；
      2. 不含否定/修改信号（如「和之前不一样」「换个口味」）。

    返回 True 表示这是复购意图，调用方应走 resolve_reorder_target 查历史订单。
    """
    msg = (user_msg or "").strip()
    if not msg:
        return False
    # 否定守门优先：含「换/不/别」等 → 不是复购
    if any(w in msg for w in _REORDER_NEGATION_WORDS):
        return False
    # 命中复购短语 → 是复购意图
    return any(w in msg for w in _REORDER_WORDS)


def resolve_reorder_target(db: Session, user_id: int, *, limit: int = 20) -> str | None:
    """从历史订单解析复购目标（最常点的那杯）。

    策略：
      1. 拉取该用户最近 `limit` 单已支付订单（按 created_at desc，索引 idx_user_created 已优化）；
      2. 按 coffee_name 统计频次，取点得最多的；
      3. 频次相同 → 取最近下单的那杯（查询已按时间倒序，遍历保留首个最高频即可）；
      4. 无历史订单 → 返回 None（调用方回退到对话历史或画像）。

    返回咖啡名（如「美式咖啡」），或 None。
    """
    try:
        orders = (
            db.query(Order)
            .filter(Order.user_id == user_id, Order.payment_status == "paid")
            .order_by(Order.created_at.desc())
            .limit(limit)
            .all()
        )
    except Exception:
        logger.warning("复购查询历史订单失败 user_id=%s", user_id, exc_info=True)
        return None

    if not orders:
        return None

    # 按频次统计：Counter 按 coffee_name 计数。
    # 查询已按时间倒序，遍历时相同频次保留先出现的（=最近下单的）。
    counter: Counter[str] = Counter()
    ordered_names: list[str] = []  # 保持时间顺序，用于频次相同时取最近
    for o in orders:
        name = (o.coffee_name or "").strip()
        if not name:
            continue
        counter[name] += 1
        if name not in ordered_names:
            ordered_names.append(name)

    if not ordered_names:
        return None

    # 取最高频；频次相同取时间最近的（ordered_names 已按最近在前排序）
    max_count = max(counter.values())
    for name in ordered_names:  # 时间倒序，首个达到 max_count 的即最近的高频款
        if counter[name] == max_count:
            return name
    return ordered_names[0]  # 兜底，理论不可达


def get_profile_hint(user_id: int) -> str:
    """读取用户画像摘要（复购日志/调试用）。复用 user_profile_service。"""
    try:
        return _get_profile_summary(user_id)
    except Exception:
        return ""
