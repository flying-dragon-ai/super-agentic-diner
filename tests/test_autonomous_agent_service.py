from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports

import asyncio
import json
import unittest
import uuid
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import models  # noqa: F401 - ensure every model is registered
from app.db.database import Base, SessionLocal, engine
from app.db.models import AgentProfile, Order, OrderItem, SkillOrderLedger, VisualizationEvent
from app.services import autonomous_agent_service as svc


def _db_reachable() -> bool:
    try:
        Base.metadata.create_all(engine)
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            return True
        finally:
            db.close()
    except Exception:
        return False


def _product(name: str = "测试自主拿铁") -> svc.AutonomousProduct:
    return svc.AutonomousProduct(
        product_id=999001,
        name=name,
        category="测试",
        base_price=str(Decimal("22.00")),
        stock=5,
        tags="测试,自主",
    )


def _perception(products: list[svc.AutonomousProduct]) -> svc.AutonomousPerception:
    return svc.AutonomousPerception(
        agent_id=1,
        now="2026-06-28T00:00:00",
        available_products=products,
        recent_event_types=["restaurant.customer_entered"],
        active_agent_count=1,
    )


class AutonomousDecisionTests(unittest.TestCase):
    def test_decide_with_available_product_builds_observable_order_simulation(self):
        product = _product()
        with patch.object(svc.random, "choice", return_value=product):
            decision = svc.decide(_perception([product]))

        self.assertEqual(decision.intent, "simulate_coffee_order")
        self.assertEqual(decision.reason, "timer_triggered_with_available_menu")
        self.assertEqual(decision.chosen_product, product.name)
        self.assertTrue(decision.decision_id)
        self.assertTrue(decision.correlation_id.startswith("auto-"))
        self.assertEqual(
            [step.action_type for step in decision.steps],
            [
                "enter_scene",
                "show_message",
                "walk_to_counter",
                "take_order",
                "walk_to_table",
                "leave_scene",
            ],
        )

    def test_decide_without_available_product_browses_and_leaves(self):
        decision = svc.decide(_perception([]))

        self.assertEqual(decision.intent, "browse_menu")
        self.assertEqual(decision.reason, "no_available_product")
        self.assertIsNone(decision.chosen_product)
        self.assertEqual(
            [step.action_type for step in decision.steps],
            ["enter_scene", "show_message", "leave_scene"],
        )


@unittest.skipUnless(_db_reachable(), "Database not reachable")
class AutonomousCycleTests(unittest.TestCase):
    def setUp(self):
        svc.reset_runtime_state_for_tests()
        self.tool_name = "test:autonomous:" + uuid.uuid4().hex[:12]
        self.display_name = "测试自主顾客"
        self.correlation_ids: list[str] = []

    def tearDown(self):
        db = SessionLocal()
        try:
            if self.correlation_ids:
                db.query(VisualizationEvent).filter(
                    VisualizationEvent.correlation_id.in_(self.correlation_ids)
                ).delete(synchronize_session=False)
            db.query(AgentProfile).filter(AgentProfile.tool_name == self.tool_name).delete(
                synchronize_session=False
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        svc.reset_runtime_state_for_tests()

    def _counts(self, db):
        return {
            "orders": db.query(Order).count(),
            "items": db.query(OrderItem).count(),
            "ledgers": db.query(SkillOrderLedger).count(),
        }

    def test_run_one_cycle_publishes_decision_and_actions_without_orders(self):
        product = _product()

        def fake_sense(_db, agent):
            return svc.AutonomousPerception(
                agent_id=agent.agent_id,
                now="2026-06-28T00:00:00",
                available_products=[product],
                recent_event_types=[],
                active_agent_count=1,
            )

        db = SessionLocal()
        try:
            before_counts = self._counts(db)
        finally:
            db.close()

        with (
            patch.object(svc, "_acquire_loop_lease", return_value=True),
            patch.object(svc, "sense", side_effect=fake_sense),
            patch.object(svc.settings, "autonomous_agent_step_interval_seconds", 0.0),
            patch.object(svc.random, "choice", return_value=product),
        ):
            decision = asyncio.run(
                svc.run_one_cycle(
                    tool_name=self.tool_name,
                    display_name=self.display_name,
                )
            )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.correlation_ids.append(decision.correlation_id)

        db = SessionLocal()
        try:
            after_counts = self._counts(db)
            events = (
                db.query(VisualizationEvent)
                .filter(VisualizationEvent.correlation_id == decision.correlation_id)
                .order_by(VisualizationEvent.event_id.asc())
                .all()
            )
        finally:
            db.close()

        self.assertEqual(after_counts, before_counts)
        self.assertEqual(events[0].event_type, "agent.autonomous.decision")
        decision_payload = json.loads(events[0].payload_json)
        self.assertTrue(decision_payload["autonomous"])
        self.assertEqual(
            decision_payload["autonomy_source"],
            "backend_agent_runtime",
        )
        self.assertEqual(
            decision_payload["decision"]["decision_id"],
            decision.decision_id,
        )

        actions = [row for row in events if row.event_type == "agent.action"]
        action_payloads = [json.loads(row.payload_json) for row in actions]
        self.assertEqual(
            [payload["action_type"] for payload in action_payloads],
            [
                "enter_scene",
                "show_message",
                "walk_to_counter",
                "take_order",
                "walk_to_table",
                "leave_scene",
            ],
        )
        for index, payload in enumerate(action_payloads, start=1):
            self.assertTrue(payload["autonomous"])
            self.assertEqual(payload["autonomy_source"], "backend_agent_runtime")
            self.assertEqual(payload["decision_id"], decision.decision_id)
            self.assertEqual(payload["plan_step"], index)
            self.assertEqual(payload["chosen_product"], product.name)
        walk_to_table = action_payloads[4]
        self.assertEqual(walk_to_table["x"], 230)
        self.assertEqual(walk_to_table["y"], 260)

    def test_status_endpoint_is_wired_to_service_snapshot(self):
        import app.main as app_main

        expected = {
            "enabled": True,
            "running": False,
            "agent_id": None,
            "display_name": "数字顾客",
            "last_seen_at": None,
            "last_decision": {"decision_id": "d1"},
            "next_run_after": None,
            "last_error": None,
        }
        app_main.app.dependency_overrides[app_main.require_admin] = lambda: object()
        try:
            with patch.object(app_main.autonomous_agent_service, "status_snapshot", return_value=expected):
                response = TestClient(app_main.app).get("/admin/autonomous-agent/status")
        finally:
            app_main.app.dependency_overrides.pop(app_main.require_admin, None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)


if __name__ == "__main__":
    unittest.main()
