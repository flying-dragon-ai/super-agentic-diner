from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.db.models import AgentProfile
from app.domain_constants import IDENTITY_STATUS_ACTIVE
from app.services.visualization_service import (
    create_visualization_event,
    encode_json,
    hash_agent_token,
    make_sprite_seed,
    visualization_hub,
)

# Fixed restaurant staff. One agent per role, created at startup and referenced
# by the orchestration layer by role (YAGNI: no "who is free" scheduling).
STAFF_ROLES: tuple[str, ...] = ("barista", "cashier", "waiter", "manager")

STAFF_TOOL_NAME = "staff:{role}"

STAFF_DISPLAY_NAME: dict[str, str] = {
    "barista": "咖啡师",
    "cashier": "收银员",
    "waiter": "服务员",
    "manager": "主管",
}

# Stable sprite seeds so staff avatars look the same across restarts.
STAFF_SPRITE_SEED: dict[str, int] = {
    "barista": 100001,
    "cashier": 100002,
    "waiter": 100003,
    "manager": 100004,
}


def _staff_tool_name(role: str) -> str:
    return STAFF_TOOL_NAME.format(role=role)


def ensure_staff_agents(db: Session) -> dict[str, AgentProfile]:
    """Idempotently create the four fixed staff agents, keyed by role."""
    staff: dict[str, AgentProfile] = {}
    for role in STAFF_ROLES:
        tool_name = _staff_tool_name(role)
        agent = (
            db.query(AgentProfile)
            .filter(AgentProfile.tool_name == tool_name)
            .order_by(AgentProfile.agent_id.asc())
            .first()
        )
        if agent is None:
            agent = AgentProfile(
                tool_name=tool_name,
                display_name=STAFF_DISPLAY_NAME[role],
                role_type=role,
                capabilities_json=encode_json([]),
                metadata_json=encode_json({"source": "staff", "staff_role": role}),
                # Staff never authenticate via token; a stable non-secret hash
                # satisfies the NOT NULL api_token_hash column.
                api_token_hash=hash_agent_token(f"staff:{role}:internal"),
                sprite_seed=STAFF_SPRITE_SEED[role],
                status=IDENTITY_STATUS_ACTIVE,
                created_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
        staff[role] = agent
    return staff


def ensure_web_customer_agent(db: Session, user_id: Any) -> AgentProfile:
    """Idempotently create/reuse a customer agent for an anonymous web user.

    Gives the web dialog path a stable customer identity so its events carry a
    real agent_id (parity with the Skill path) instead of an anonymous one.
    """
    key = str(user_id)[:96]
    tool_name = f"web:customer:{key}"
    agent = (
        db.query(AgentProfile)
        .filter(AgentProfile.tool_name == tool_name)
        .order_by(AgentProfile.agent_id.asc())
        .first()
    )
    if agent is None:
        agent = AgentProfile(
            tool_name=tool_name,
            display_name=f"Web 用户 {key}",
            role_type="customer",
            capabilities_json=encode_json([]),
            metadata_json=encode_json({"source": "web", "user_id": key}),
            api_token_hash=hash_agent_token(f"web:{key}:internal"),
            sprite_seed=make_sprite_seed(),
            status=IDENTITY_STATUS_ACTIVE,
            created_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
    return agent


def _staff_payload(agent: AgentProfile, action_type: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": agent.agent_id,
        "tool_name": agent.tool_name,
        "display_name": agent.display_name,
        "role_type": agent.role_type,
        "sprite_seed": agent.sprite_seed,
        "action_type": action_type,
    }
    payload.update(extra)
    return payload


def publish_staff_action(
    db: Session,
    staff: Mapping[str, AgentProfile],
    role: str,
    action_type: str,
    *,
    correlation_id: str | None = None,
    **extra: Any,
) -> None:
    """Broadcast a staff ``agent.action`` event.

    Failures are swallowed (with a rollback) so visualization orchestration can
    never break the order/payment business flow.
    """
    agent = staff.get(role)
    if agent is None:
        return
    try:
        message = create_visualization_event(
            db,
            event_type="agent.action",
            payload=_staff_payload(agent, action_type, **extra),
            agent_id=agent.agent_id,
            correlation_id=correlation_id,
        )
        visualization_hub.broadcast_from_sync(message)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def orchestrate_staff_node(
    db: Session,
    staff: Mapping[str, AgentProfile],
    node: str,
    correlation_id: str | None,
) -> None:
    """Drive the fixed staff team at a completion-flow business node.

    Maps each existing business event to staff actions so a customer's order is
    served end-to-end: waiter greets -> cashier rings up -> barista brews ->
    waiter delivers -> staff return to stations.
    """
    if node == "payment_completed":
        publish_staff_action(db, staff, "waiter", "walk_to_counter", correlation_id=correlation_id)
        publish_staff_action(db, staff, "cashier", "take_order", correlation_id=correlation_id)
    elif node == "preparation_progress":
        publish_staff_action(db, staff, "barista", "prepare_coffee", correlation_id=correlation_id)
    elif node == "order_ready":
        # Barista finishes active prep and returns to station.
        publish_staff_action(db, staff, "barista", "enter_scene", correlation_id=correlation_id)
    elif node == "order_delivered":
        publish_staff_action(db, staff, "waiter", "deliver_order", correlation_id=correlation_id)
    elif node == "customer_left":
        publish_staff_action(db, staff, "waiter", "enter_scene", correlation_id=correlation_id)
        publish_staff_action(db, staff, "cashier", "enter_scene", correlation_id=correlation_id)
