"""需求榜单 + 认领任务服务。

所有登录用户可以发布需求和认领需求。
状态流转：open（待认领）→ claimed（进行中）→ done（已完成）。

需求动态通过 visualization_hub 实时广播到监控大屏，管理员可一眼看到
最新发布/认领/完成的需求。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Demand, UserAccount

logger = logging.getLogger(__name__)

DEMAND_STATUS_OPEN = "open"
DEMAND_STATUS_CLAIMED = "claimed"
DEMAND_STATUS_DONE = "done"


def _broadcast_demand_event(action: str, demand: Demand, account: UserAccount) -> None:
    """将需求动态广播到可视化 WS，供监控大屏实时查看。

    采用 transient 广播（不入快照缓冲），避免历史动态在场景重放时刷屏。
    action 取值：created / claimed / completed
    """
    try:
        from app.services.visualization_service import visualization_hub
        visualization_hub.broadcast_transient_from_sync({
            "type": "demand.event",
            "payload": {
                "action": action,
                "demand_id": demand.demand_id,
                "title": demand.title,
                "status": demand.status,
                "creator_id": demand.creator_id,
                "creator_name": account.nickname or account.username,
                "claimer_id": demand.claimer_id,
                "reward_credits": demand.reward_credits or 0,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        })
    except Exception:
        pass  # 广播失败不影响主流程


def _demand_to_dict(demand: Demand, creator: UserAccount | None = None, claimer: UserAccount | None = None) -> dict[str, Any]:
    """序列化需求对象为 API 响应字典。"""
    return {
        "demand_id": demand.demand_id,
        "title": demand.title,
        "description": demand.description or "",
        "category": demand.category or "",
        "reward_credits": demand.reward_credits or 0,
        "status": demand.status,
        "creator_id": demand.creator_id,
        "creator_name": (creator.nickname or creator.username) if creator else None,
        "claimer_id": demand.claimer_id,
        "claimer_name": (claimer.nickname or claimer.username) if claimer else None,
        "created_at": demand.created_at.isoformat() + "Z" if demand.created_at else None,
        "claimed_at": demand.claimed_at.isoformat() + "Z" if demand.claimed_at else None,
        "completed_at": demand.completed_at.isoformat() + "Z" if demand.completed_at else None,
    }


def create_demand(
    db: Session,
    account: UserAccount,
    title: str,
    description: str = "",
    category: str = "",
    reward_credits: int = 0,
) -> dict[str, Any]:
    """发布一个新需求。"""
    demand = Demand(
        title=title.strip()[:128],
        description=(description or "").strip()[:2000],
        category=(category or "").strip()[:32] or None,
        reward_credits=max(0, int(reward_credits or 0)),
        status=DEMAND_STATUS_OPEN,
        creator_id=account.account_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(demand)
    db.commit()
    db.refresh(demand)
    _broadcast_demand_event("created", demand, account)
    return _demand_to_dict(demand, creator=account)


def list_demands(
    db: Session,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """获取需求列表，按创建时间倒序。支持按状态过滤。"""
    query = db.query(Demand)
    if status and status in (DEMAND_STATUS_OPEN, DEMAND_STATUS_CLAIMED, DEMAND_STATUS_DONE):
        query = query.filter(Demand.status == status)
    demands = query.order_by(Demand.created_at.desc()).limit(min(max(limit, 1), 200)).all()
    if not demands:
        return []

    # 批量查询关联的用户名
    creator_ids = {d.creator_id for d in demands}
    claimer_ids = {d.claimer_id for d in demands if d.claimer_id}
    user_ids = creator_ids | claimer_ids
    users = db.query(UserAccount).filter(UserAccount.account_id.in_(user_ids)).all() if user_ids else []
    user_map = {u.account_id: u for u in users}

    return [
        _demand_to_dict(
            d,
            creator=user_map.get(d.creator_id),
            claimer=user_map.get(d.claimer_id) if d.claimer_id else None,
        )
        for d in demands
    ]


def claim_demand(db: Session, account: UserAccount, demand_id: int) -> dict[str, Any]:
    """认领一个需求。不能认领自己发布的需求。"""
    demand = db.query(Demand).filter(Demand.demand_id == demand_id).first()
    if not demand:
        raise ValueError("需求不存在")
    if demand.status != DEMAND_STATUS_OPEN:
        raise ValueError(f"当前状态({demand.status})不可认领")
    if demand.creator_id == account.account_id:
        raise ValueError("不能认领自己发布的需求")

    demand.claimer_id = account.account_id
    demand.status = DEMAND_STATUS_CLAIMED
    demand.claimed_at = datetime.utcnow()
    demand.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(demand)

    creator = db.query(UserAccount).filter(UserAccount.account_id == demand.creator_id).first()
    _broadcast_demand_event("claimed", demand, account)
    return _demand_to_dict(demand, creator=creator, claimer=account)


def complete_demand(db: Session, account: UserAccount, demand_id: int) -> dict[str, Any]:
    """完成一个需求。仅创建者或认领者可操作。"""
    demand = db.query(Demand).filter(Demand.demand_id == demand_id).first()
    if not demand:
        raise ValueError("需求不存在")
    if demand.status != DEMAND_STATUS_CLAIMED:
        raise ValueError(f"当前状态({demand.status})不可完成")
    is_creator = demand.creator_id == account.account_id
    is_claimer = demand.claimer_id == account.account_id
    if not (is_creator or is_claimer):
        raise ValueError("仅需求发布者或认领者可完成")

    demand.status = DEMAND_STATUS_DONE
    demand.completed_at = datetime.utcnow()
    demand.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(demand)

    creator = db.query(UserAccount).filter(UserAccount.account_id == demand.creator_id).first()
    claimer = db.query(UserAccount).filter(UserAccount.account_id == demand.claimer_id).first() if demand.claimer_id else None
    _broadcast_demand_event("completed", demand, account)
    return _demand_to_dict(demand, creator=creator, claimer=claimer)


def get_recent_demand_feed(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    """获取最近的需求动态，供监控大屏实时查看。按更新时间倒序。"""
    demands = (
        db.query(Demand)
        .order_by(Demand.updated_at.desc())
        .limit(min(max(limit, 1), 50))
        .all()
    )
    if not demands:
        return []

    creator_ids = {d.creator_id for d in demands}
    claimer_ids = {d.claimer_id for d in demands if d.claimer_id}
    user_ids = creator_ids | claimer_ids
    users = db.query(UserAccount).filter(UserAccount.account_id.in_(user_ids)).all() if user_ids else []
    user_map = {u.account_id: u for u in users}

    feed = []
    for d in demands:
        creator = user_map.get(d.creator_id)
        claimer = user_map.get(d.claimer_id) if d.claimer_id else None
        item = _demand_to_dict(d, creator=creator, claimer=claimer)
        # 标记最新动作
        if d.completed_at:
            item["latest_action"] = "completed"
            item["action_time"] = d.completed_at.isoformat() + "Z" if d.completed_at else None
        elif d.claimed_at:
            item["latest_action"] = "claimed"
            item["action_time"] = d.claimed_at.isoformat() + "Z" if d.claimed_at else None
        else:
            item["latest_action"] = "created"
            item["action_time"] = d.created_at.isoformat() + "Z" if d.created_at else None
        feed.append(item)
    return feed
