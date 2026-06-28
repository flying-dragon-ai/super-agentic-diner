"""Autonomous digital customer runtime.

The 3D avatar is driven from this backend loop: sense cafe state, decide a
small plan, publish the decision, then execute visible agent actions. v1 is
intentionally non-transactional: it does not create orders, consume inventory,
touch wallets, or call EvoMap payment APIs.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final

from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import AgentProfile, Product, VisualizationEvent
from app.domain_constants import IDENTITY_STATUS_ACTIVE, PRODUCT_STATUS_AVAILABLE
from app.memory._redis_client import get_redis_client
from app.services import staff_service
from app.services.visualization_service import (
    encode_json,
    hash_agent_token,
    publish_visualization_event,
)

AUTONOMOUS_TOOL_NAME: Final[str] = "evomap:autonomous_customer"
AUTONOMOUS_DISPLAY_NAME: Final[str] = "数字顾客"
AUTONOMOUS_SPRITE_SEED: Final[int] = 200001
AUTONOMOUS_USER_ID: Final[int] = 1
AUTONOMOUS_LOOP_LOCK_KEY: Final[str] = "coffee:autonomous:loop-lock"

_last_decision: dict[str, Any] | None = None
_next_run_after: datetime | None = None
_last_error: str | None = None
_running = False


@dataclass(slots=True)
class AutonomousProduct:
    product_id: int
    name: str
    category: str | None
    base_price: str
    stock: int
    tags: str | None = None


@dataclass(slots=True)
class AutonomousPerception:
    agent_id: int
    now: str
    available_products: list[AutonomousProduct]
    recent_event_types: list[str]
    active_agent_count: int


@dataclass(slots=True)
class AutonomousActionStep:
    action_type: str
    wait_seconds: float = 0.0
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AutonomousDecision:
    decision_id: str
    correlation_id: str
    intent: str
    reason: str
    chosen_product: str | None
    steps: list[AutonomousActionStep]
    created_at: str

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [step.action_type for step in self.steps]
        return data


def _now() -> datetime:
    return datetime.utcnow()


def _agent_metadata() -> dict[str, Any]:
    return {
        "source": "autonomous",
        "user_id": AUTONOMOUS_USER_ID,
        "autonomy_source": "backend_agent_runtime",
    }


def ensure_autonomous_customer_agent(
    db: Session,
    *,
    tool_name: str = AUTONOMOUS_TOOL_NAME,
    display_name: str = AUTONOMOUS_DISPLAY_NAME,
) -> AgentProfile:
    """Idempotently create/reuse the autonomous digital customer agent."""
    existing = db.query(AgentProfile).filter(AgentProfile.tool_name == tool_name).first()
    if existing:
        return existing
    agent = AgentProfile(
        tool_name=tool_name,
        display_name=display_name,
        role_type="customer",
        capabilities_json=encode_json(["autonomous_customer"]),
        metadata_json=encode_json(_agent_metadata()),
        api_token_hash=hash_agent_token("autonomous:internal"),
        sprite_seed=AUTONOMOUS_SPRITE_SEED,
        status=IDENTITY_STATUS_ACTIVE,
        created_at=_now(),
        last_seen_at=_now(),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def sense(db: Session, agent: AgentProfile) -> AutonomousPerception:
    products = (
        db.query(Product)
        .filter(Product.status == PRODUCT_STATUS_AVAILABLE, Product.stock > 0)
        .order_by(Product.product_id.asc())
        .limit(12)
        .all()
    )
    recent_events = (
        db.query(VisualizationEvent.event_type)
        .order_by(VisualizationEvent.created_at.desc())
        .limit(8)
        .all()
    )
    active_cutoff = _now() - timedelta(seconds=settings.autonomous_agent_status_ttl_seconds)
    active_agent_count = (
        db.query(AgentProfile)
        .filter(
            AgentProfile.status == IDENTITY_STATUS_ACTIVE,
            AgentProfile.last_seen_at >= active_cutoff,
        )
        .count()
    )
    return AutonomousPerception(
        agent_id=agent.agent_id,
        now=_now().isoformat(),
        available_products=[
            AutonomousProduct(
                product_id=p.product_id,
                name=p.name,
                category=p.category,
                base_price=str(p.base_price),
                stock=p.stock,
                tags=p.tags,
            )
            for p in products
        ],
        recent_event_types=[row[0] for row in recent_events],
        active_agent_count=active_agent_count,
    )


def decide(perception: AutonomousPerception) -> AutonomousDecision:
    decision_id = uuid.uuid4().hex
    correlation_id = "auto-" + decision_id[:12]
    created_at = _now().isoformat()
    if not perception.available_products:
        return AutonomousDecision(
            decision_id=decision_id,
            correlation_id=correlation_id,
            intent="browse_menu",
            reason="no_available_product",
            chosen_product=None,
            created_at=created_at,
            steps=[
                AutonomousActionStep(
                    "enter_scene",
                    message="我先看看今天还有什么可以点。",
                ),
                AutonomousActionStep(
                    "show_message",
                    wait_seconds=settings.autonomous_agent_step_interval_seconds,
                    message="看起来暂时没有可点的咖啡，我下次再来。",
                ),
                AutonomousActionStep(
                    "leave_scene",
                    wait_seconds=settings.autonomous_agent_step_interval_seconds,
                ),
            ],
        )

    # Stable enough to avoid always picking the first product, deterministic enough
    # that tests can assert membership rather than an exact random branch.
    product = random.choice(perception.available_products)
    return AutonomousDecision(
        decision_id=decision_id,
        correlation_id=correlation_id,
        intent="simulate_coffee_order",
        reason="timer_triggered_with_available_menu",
        chosen_product=product.name,
        created_at=created_at,
        steps=[
            AutonomousActionStep(
                "enter_scene",
                message=f"我想试试{product.name}，去吧台看看。",
            ),
            AutonomousActionStep(
                "show_message",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
                message=f"今天想喝{product.name}。",
            ),
            AutonomousActionStep(
                "walk_to_counter",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
            ),
            AutonomousActionStep(
                "take_order",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
                message=f"模拟点单：{product.name}",
            ),
            AutonomousActionStep(
                "walk_to_table",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
                payload={"x": 230, "y": 260},
            ),
            AutonomousActionStep(
                "leave_scene",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
            ),
        ],
    )


def _decision_payload(
    decision: AutonomousDecision,
    perception: AutonomousPerception,
) -> dict[str, Any]:
    return {
        "autonomous": True,
        "autonomy_source": "backend_agent_runtime",
        "decision": decision.public_dict(),
        "perception": {
            "available_product_count": len(perception.available_products),
            "recent_event_types": perception.recent_event_types,
            "active_agent_count": perception.active_agent_count,
        },
    }


def publish_decision(
    db: Session,
    agent: AgentProfile,
    decision: AutonomousDecision,
    perception: AutonomousPerception,
) -> None:
    publish_visualization_event(
        db,
        "agent.autonomous.decision",
        _decision_payload(decision, perception),
        agent_id=agent.agent_id,
        correlation_id=decision.correlation_id,
    )


def _step_payload(
    decision: AutonomousDecision,
    step: AutonomousActionStep,
    index: int,
) -> dict[str, Any]:
    payload = {
        "autonomous": True,
        "autonomy_source": "backend_agent_runtime",
        "decision_id": decision.decision_id,
        "plan_step": index,
        "intent": decision.intent,
        "reason": decision.reason,
        "chosen_product": decision.chosen_product,
        "trigger": "timer",
        "payload": step.payload,
    }
    payload.update(step.payload)
    if step.message:
        payload["message"] = step.message
        payload["text"] = step.message
    return payload


def publish_action_step(
    db: Session,
    agent: AgentProfile,
    decision: AutonomousDecision,
    step: AutonomousActionStep,
    index: int,
) -> None:
    agent.last_seen_at = _now()
    db.commit()
    db.refresh(agent)
    staff_service.publish_agent_action(
        db,
        agent,
        step.action_type,
        correlation_id=decision.correlation_id,
        **_step_payload(decision, step, index),
    )


async def execute_decision(
    db: Session,
    agent: AgentProfile,
    decision: AutonomousDecision,
) -> None:
    for index, step in enumerate(decision.steps, start=1):
        if step.wait_seconds > 0:
            await asyncio.sleep(step.wait_seconds)
        publish_action_step(db, agent, decision, step, index)


async def run_one_cycle(
    *,
    tool_name: str = AUTONOMOUS_TOOL_NAME,
    display_name: str = AUTONOMOUS_DISPLAY_NAME,
) -> AutonomousDecision | None:
    """Run one autonomous decision/execution cycle.

    Returns None when another worker owns the short lease.
    """
    global _last_decision, _last_error, _running
    if not _acquire_loop_lease():
        return None
    _running = True
    db = SessionLocal()
    try:
        agent = ensure_autonomous_customer_agent(
            db, tool_name=tool_name, display_name=display_name
        )
        perception = sense(db, agent)
        decision = decide(perception)
        publish_decision(db, agent, decision, perception)
        await execute_decision(db, agent, decision)
        _last_decision = decision.public_dict()
        _last_error = None
        return decision
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _last_error = exc.__class__.__name__
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()
        _running = False


def _acquire_loop_lease() -> bool:
    if settings.use_fakeredis:
        return True
    try:
        client = get_redis_client(decode_responses=True)
        return bool(
            client.set(
                AUTONOMOUS_LOOP_LOCK_KEY,
                uuid.uuid4().hex,
                nx=True,
                ex=max(30, int(settings.autonomous_agent_step_interval_seconds * 10)),
            )
        )
    except Exception:
        return True


def _next_interval_seconds() -> float:
    return random.uniform(
        settings.autonomous_agent_interval_min_seconds,
        settings.autonomous_agent_interval_max_seconds,
    )


async def autonomous_loop() -> None:
    """Background loop: one autonomous session every configured interval."""
    global _next_run_after
    while True:
        try:
            await run_one_cycle()
        except asyncio.CancelledError:
            raise
        interval = _next_interval_seconds()
        _next_run_after = _now() + timedelta(seconds=interval)
        await asyncio.sleep(interval)


def status_snapshot(db: Session) -> dict[str, Any]:
    agent = (
        db.query(AgentProfile)
        .filter(AgentProfile.tool_name == AUTONOMOUS_TOOL_NAME)
        .first()
    )
    return {
        "enabled": settings.autonomous_agent_enabled,
        "running": _running,
        "agent_id": agent.agent_id if agent else None,
        "display_name": agent.display_name if agent else AUTONOMOUS_DISPLAY_NAME,
        "last_seen_at": agent.last_seen_at.isoformat() if agent else None,
        "last_decision": _last_decision,
        "next_run_after": _next_run_after.isoformat() if _next_run_after else None,
        "last_error": _last_error,
    }


def reset_runtime_state_for_tests() -> None:
    global _last_decision, _next_run_after, _last_error, _running
    _last_decision = None
    _next_run_after = None
    _last_error = None
    _running = False
