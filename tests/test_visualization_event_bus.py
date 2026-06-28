from __future__ import annotations

import asyncio
import unittest
import uuid

from app.db.database import SessionLocal
from app.db.models import VisualizationEvent
from app.services.visualization_service import (
    VisualizationHub,
    create_visualization_events,
)


class _FakeWebSocket:
    def __init__(self, *, block_after_snapshot: bool = False) -> None:
        self.accepted = False
        self.sent: list[dict] = []
        self.block_after_snapshot = block_after_snapshot
        self._unblock = asyncio.Event()

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        if self.block_after_snapshot and message.get("type") != "scene.snapshot":
            await self._unblock.wait()
        self.sent.append(message)

    def unblock(self) -> None:
        self._unblock.set()


class VisualizationHubQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_connection_does_not_block_fast_connection(self) -> None:
        hub = VisualizationHub()
        fast = _FakeWebSocket()
        slow = _FakeWebSocket(block_after_snapshot=True)
        await hub.connect(fast, agents=[])
        await hub.connect(slow, agents=[])

        await asyncio.wait_for(
            hub.broadcast(
                {
                    "message_id": "queue-test-" + uuid.uuid4().hex,
                    "type": "agent.action",
                    "event_id": None,
                    "agent_id": 1,
                    "payload": {"action_type": "enter_scene"},
                    "created_at": "2026-06-28T00:00:00",
                }
            ),
            timeout=0.1,
        )
        await asyncio.sleep(0.05)

        self.assertTrue(
            any(message.get("type") == "agent.action" for message in fast.sent),
            "fast websocket should receive the event even while another writer is blocked",
        )
        slow.unblock()
        hub.disconnect(fast)
        hub.disconnect(slow)

    async def test_duplicate_event_id_is_not_sent_twice(self) -> None:
        hub = VisualizationHub()
        websocket = _FakeWebSocket()
        await hub.connect(websocket, agents=[])
        message = {
            "event_id": 123456,
            "type": "agent.action",
            "agent_id": 1,
            "payload": {"action_type": "enter_scene"},
            "created_at": "2026-06-28T00:00:00",
        }

        await hub.broadcast(message)
        await hub.broadcast(dict(message))
        await asyncio.sleep(0.05)

        sent = [item for item in websocket.sent if item.get("type") == "agent.action"]
        self.assertEqual(len(sent), 1)
        hub.disconnect(websocket)


class VisualizationBatchPersistTests(unittest.TestCase):
    def test_create_visualization_events_persists_in_input_order(self) -> None:
        correlation_id = "batch-test-" + uuid.uuid4().hex
        db = SessionLocal()
        try:
            messages = create_visualization_events(
                db,
                [
                    {
                        "event_type": "restaurant.payment_completed",
                        "payload": {"step": 1},
                        "correlation_id": correlation_id,
                    },
                    {
                        "event_type": "restaurant.order_delivered",
                        "payload": {"step": 2},
                        "correlation_id": correlation_id,
                    },
                ],
            )

            self.assertEqual(
                [message["type"] for message in messages],
                ["restaurant.payment_completed", "restaurant.order_delivered"],
            )
            self.assertLess(messages[0]["event_id"], messages[1]["event_id"])
        finally:
            db.query(VisualizationEvent).filter(
                VisualizationEvent.correlation_id == correlation_id
            ).delete(synchronize_session=False)
            db.commit()
            db.close()


if __name__ == "__main__":
    unittest.main()
