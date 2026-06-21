"""Autonomous digital customer agent — P1: simulated buy-coffee loop.

A single digital customer (``evomap:autonomous_customer``) walks itself through
a buy-coffee session in the 3D cafe every ~45-75s: enter → walk_to_counter →
take_order → leave_scene. Each step broadcasts an ``agent.action`` event so the
3D avatar moves visibly; no real order is placed in P1 (that's P2).

The agent uses ``role_type='customer'`` so it flows through ``_build_snapshot_agents``
(online customer) — ``customer_enter_scene`` refreshes ``last_seen_at`` to keep it
inside the heartbeat window for the whole session.

P2 will replace the simulated take_order with a real order via order_service
(agent's ``user_id=1`` wallet). P3 will let local ``agent_experience`` guide the
coffee choice. P4 adds sit_on_couch / wander_lounge play actions.
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Final

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import AgentProfile
from app.domain_constants import IDENTITY_STATUS_ACTIVE
from app.services import staff_service
from app.services.visualization_service import encode_json, hash_agent_token

AUTONOMOUS_TOOL_NAME: Final[str] = "evomap:autonomous_customer"
AUTONOMOUS_DISPLAY_NAME: Final[str] = "数字顾客"
# Stable seed so the avatar looks the same across restarts; outside the staff
# range (100001-100004) and web-customer random range.
AUTONOMOUS_SPRITE_SEED: Final[int] = 200001
# P2 will use this wallet for real orders (metadata-stored; agent_profile has no
# user_id column). seed user_id=1 has balance 100.
AUTONOMOUS_USER_ID: Final[int] = 1

# Session cadence: one buy-coffee session every 45-75s.
SESSION_INTERVAL_MIN: Final[float] = 45.0
SESSION_INTERVAL_MAX: Final[float] = 75.0
# Seconds between action steps inside a session (lets the 3D avatar visibly move).
STEP_INTERVAL: Final[float] = 4.0


def ensure_autonomous_customer_agent(db: Session) -> AgentProfile:
    """Idempotently create/reuse the autonomous digital customer agent."""
    existing = (
        db.query(AgentProfile)
        .filter(AgentProfile.tool_name == AUTONOMOUS_TOOL_NAME)
        .first()
    )
    if existing:
        return existing
    agent = AgentProfile(
        tool_name=AUTONOMOUS_TOOL_NAME,
        display_name=AUTONOMOUS_DISPLAY_NAME,
        role_type="customer",
        capabilities_json=encode_json([]),
        metadata_json=encode_json(
            {"source": "autonomous", "user_id": AUTONOMOUS_USER_ID}
        ),
        # Autonomous agent never authenticates via token; a stable non-secret
        # hash satisfies the NOT NULL api_token_hash column.
        api_token_hash=hash_agent_token("autonomous:internal"),
        sprite_seed=AUTONOMOUS_SPRITE_SEED,
        status=IDENTITY_STATUS_ACTIVE,
        created_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


async def _broadcast_step(agent_id: int, action_type: str, *, enter: bool) -> None:
    """Broadcast one action for the agent, using a fresh DB session.

    A fresh session per step avoids stale state across the long async gaps; the
    business-loop pattern mirrors _skill_presence_sweep_loop.
    """
    db = SessionLocal()
    try:
        agent = (
            db.query(AgentProfile)
            .filter(AgentProfile.agent_id == agent_id)
            .first()
        )
        if agent is None:
            return
        # enter_scene goes through customer_enter_scene so last_seen_at is
        # refreshed (keeps the avatar inside the snapshot heartbeat window for
        # late-connecting clients and wards off the skill sweep mid-session).
        if enter:
            staff_service.customer_enter_scene(db, agent)
        else:
            staff_service.publish_agent_action(db, agent, action_type)
    finally:
        db.close()


async def _run_buy_coffee_session(agent_id: int) -> None:
    """One autonomous buy-coffee session (P1: simulated, no real order)."""
    await _broadcast_step(agent_id, "enter_scene", enter=True)
    await asyncio.sleep(STEP_INTERVAL)
    await _broadcast_step(agent_id, "walk_to_counter", enter=False)
    await asyncio.sleep(STEP_INTERVAL)
    await _broadcast_step(agent_id, "take_order", enter=False)
    await asyncio.sleep(STEP_INTERVAL)
    await _broadcast_step(agent_id, "leave_scene", enter=False)


async def autonomous_loop() -> None:
    """Background loop: run a buy-coffee session every 45-75s. Best-effort.

    Never crashes the loop on errors (visualization must never block business).
    ``CancelledError`` re-raises so shutdown can stop the loop cleanly.
    """
    while True:
        try:
            db = SessionLocal()
            try:
                agent_id = ensure_autonomous_customer_agent(db).agent_id
            finally:
                db.close()
            await _run_buy_coffee_session(agent_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Swallow — never kill the autonomous loop on a transient error.
            pass
        await asyncio.sleep(random.uniform(SESSION_INTERVAL_MIN, SESSION_INTERVAL_MAX))
