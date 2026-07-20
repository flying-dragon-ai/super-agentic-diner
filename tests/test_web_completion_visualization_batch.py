from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from app import main as app_main


class WebCompletionVisualizationBatchTests(unittest.TestCase):
    def test_web_completion_flow_publishes_one_ordered_batch(self) -> None:
        req = SimpleNamespace(
            user_id=42,
            request_id="web-batch-test",
        )
        orders = [
            SimpleNamespace(order_id=101, coffee_name="Americano", amount=Decimal("22.00")),
        ]
        staff = {
            "cashier": SimpleNamespace(
                agent_id=201,
                tool_name="staff:cashier",
                display_name="Cashier",
                role_type="cashier",
                sprite_seed=100002,
            ),
            "barista": SimpleNamespace(
                agent_id=202,
                tool_name="staff:barista",
                display_name="Barista",
                role_type="barista",
                sprite_seed=100001,
            ),
            "waiter": SimpleNamespace(
                agent_id=203,
                tool_name="staff:waiter",
                display_name="Waiter",
                role_type="waiter",
                sprite_seed=100003,
            ),
        }
        captured: list[list[dict]] = []

        with (
            patch.object(app_main.staff_service, "ensure_staff_agents", return_value=staff),
            patch.object(app_main, "_try_publish_visualization_events", side_effect=lambda _db, events: captured.append(events)),
            patch.object(app_main.user_profile_service, "summarize_async"),
        ):
            app_main._publish_web_completion_flow(
                SimpleNamespace(),
                req=req,
                consumer_url="http://example.test/",
                orders=orders,
                agent_id=42,
            )

        self.assertEqual(len(captured), 1)
        event_types = [event["event_type"] for event in captured[0]]
        self.assertEqual(
            event_types,
            [
                "restaurant.payment_completed",
                "agent.action",
                "restaurant.preparation_progress",
                "agent.action",
                "restaurant.preparation_progress",
                "agent.action",
                "restaurant.preparation_progress",
                "agent.action",
                "restaurant.order_ready",
                "agent.action",
                "restaurant.order_delivered",
                "agent.action",
                "restaurant.customer_reviewed",
                "restaurant.customer_left",
                "agent.action",
                "agent.action",
            ],
        )
        actions = [
            event["payload"].get("action_type")
            for event in captured[0]
            if event["event_type"] == "agent.action"
        ]
        self.assertEqual(
            actions,
            [
                "take_order",
                "prepare_coffee",
                "prepare_coffee",
                "prepare_coffee",
                "enter_scene",
                "deliver_order",
                "enter_scene",
                "enter_scene",
            ],
        )


if __name__ == "__main__":
    unittest.main()
