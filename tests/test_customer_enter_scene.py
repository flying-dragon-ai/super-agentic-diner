"""专项测试：网页/Skill 点单时顾客 enter_scene 事件产生并归属顾客 agent。

覆盖修复路径（2026-06-21）：
- /chat（匿名 user_id）→ ensure_web_customer_agent + customer_enter_scene
- /skill/orders → customer_enter_scene（即使订单 400/402 也应先广播 enter_scene）
- restaurant.customer_entered 事件须携带顾客 agent_id（不再是 None）
"""
from __future__ import annotations

import json
import unittest
import uuid

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import AgentProfile, VisualizationEvent
from app.main import app


def _latest_action(agent_id: int, action_type: str) -> VisualizationEvent | None:
    db = SessionLocal()
    try:
        rows = (
            db.query(VisualizationEvent)
            .filter(
                VisualizationEvent.event_type == "agent.action",
                VisualizationEvent.agent_id == agent_id,
            )
            .order_by(VisualizationEvent.event_id.desc())
            .all()
        )
        for row in rows:
            payload = json.loads(row.payload_json)
            if payload.get("action_type") == action_type:
                return row
        return None
    finally:
        db.close()


class CustomerEnterSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_chat_creates_customer_agent_and_broadcasts_enter_scene(self) -> None:
        uid = 990000 + (uuid.uuid4().int % 9999)
        rid = "enter-web-" + uuid.uuid4().hex[:8]
        resp = self.client.post(
            "/chat",
            json={"user_id": uid, "message": "美式", "request_id": rid},
        )
        self.assertEqual(resp.status_code, 200)

        db = SessionLocal()
        try:
            agent = (
                db.query(AgentProfile)
                .filter(AgentProfile.tool_name == f"web:customer:{uid}")
                .first()
            )
            ce = (
                db.query(VisualizationEvent)
                .filter(
                    VisualizationEvent.event_type == "restaurant.customer_entered",
                    VisualizationEvent.correlation_id == rid,
                )
                .first()
            )
        finally:
            db.close()

        self.assertIsNotNone(agent, "web customer agent must be created on /chat")
        self.assertEqual(agent.role_type, "customer")
        self.assertIsNotNone(ce, "restaurant.customer_entered must be emitted")
        self.assertEqual(
            ce.agent_id,
            agent.agent_id,
            "customer_entered must carry the customer agent_id (not None)",
        )
        self.assertIsNotNone(
            _latest_action(agent.agent_id, "enter_scene"),
            "enter_scene agent.action must be broadcast for the customer",
        )

    def test_skill_order_broadcasts_enter_scene_even_when_order_fails(self) -> None:
        node = "enter-skill-" + uuid.uuid4().hex[:8]
        reg = self.client.post(
            "/skill/register",
            json={
                "tool_name": "codex",
                "display_name": "EnterTest",
                "evomap_node_id": node,
                "role_type": "customer",
                "capabilities": ["a2a_super_order"],
            },
        ).json()
        agent_id = reg["agent_id"]
        # 裸"拿铁"短名 → coffee_not_resolved (400)，但 enter_scene 在解析之前已广播。
        self.client.post(
            "/skill/orders",
            json={
                "consumer_id": reg["consumer_id"],
                "agent_id": agent_id,
                "auto_confirm": True,
                "message": "拿铁",
                "request_id": "enter-skill-" + uuid.uuid4().hex[:8],
            },
            headers={"X-Agent-Token": reg["api_token"]},
        )
        self.assertIsNotNone(
            _latest_action(agent_id, "enter_scene"),
            "enter_scene must fire even when the order later fails to resolve",
        )


if __name__ == "__main__":
    unittest.main()
