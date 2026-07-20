from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports
import asyncio
import json
import unittest
import uuid
from unittest.mock import patch

from app.db.database import SessionLocal
from app.db.models import VisualizationEvent
from app.services.visualization_service import (
    VisualizationEventBus,
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


class VisualizationEventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_many_uses_batch_envelope_and_preserves_order(self) -> None:
        hub = VisualizationHub()
        websocket = _FakeWebSocket()
        await hub.connect(websocket, agents=[])
        bus = VisualizationEventBus(hub)
        messages = [
            {
                "event_id": 900001,
                "type": "restaurant.payment_completed",
                "agent_id": 1,
                "payload": {"step": 1},
                "created_at": "2026-06-28T00:00:00",
            },
            {
                "event_id": 900002,
                "type": "restaurant.order_delivered",
                "agent_id": 1,
                "payload": {"step": 2},
                "created_at": "2026-06-28T00:00:01",
            },
        ]

        with patch.object(bus, "_publish_to_redis_envelope") as publish_mock:
            enriched = await bus.publish_many(messages, replay=True)
        await asyncio.sleep(0.05)

        sent_types = [item.get("type") for item in websocket.sent if item.get("event_id")]
        self.assertEqual(sent_types, ["restaurant.payment_completed", "restaurant.order_delivered"])
        envelope = publish_mock.call_args.args[0]
        self.assertEqual([item["event_id"] for item in envelope["messages"]], [900001, 900002])
        self.assertTrue(all(item.get("message_id") for item in enriched))
        hub.disconnect(websocket)

    async def test_redis_batch_envelope_fans_out_as_ordered_events(self) -> None:
        hub = VisualizationHub()
        websocket = _FakeWebSocket()
        await hub.connect(websocket, agents=[])
        bus = VisualizationEventBus(hub)
        bus._loop = asyncio.get_running_loop()
        bus._handle_redis_message(
            json.dumps(
                {
                    "replay": True,
                    "messages": [
                        {
                            "message_id": "redis-batch-a-" + uuid.uuid4().hex,
                            "type": "restaurant.payment_completed",
                            "event_id": None,
                            "agent_id": 1,
                            "payload": {"step": 1},
                            "created_at": "2026-06-28T00:00:00",
                        },
                        {
                            "message_id": "redis-batch-b-" + uuid.uuid4().hex,
                            "type": "restaurant.order_delivered",
                            "event_id": None,
                            "agent_id": 1,
                            "payload": {"step": 2},
                            "created_at": "2026-06-28T00:00:01",
                        },
                    ],
                }
            )
        )
        await asyncio.sleep(0.05)

        sent_types = [
            item.get("type")
            for item in websocket.sent
            if item.get("type", "").startswith("restaurant.")
        ]
        self.assertEqual(sent_types, ["restaurant.payment_completed", "restaurant.order_delivered"])
        hub.disconnect(websocket)


class VisualizationRedisReconnectTests(unittest.TestCase):
    def test_listener_reconnects_after_subscribe_failure(self) -> None:
        bus = VisualizationEventBus(VisualizationHub())

        class _Stop:
            stopped = False

            def is_set(self) -> bool:
                return self.stopped

            def wait(self, _timeout: float) -> bool:
                return False

        class _FailingPubSub:
            def subscribe(self, _channel: str) -> None:
                pass

            def listen(self):
                raise RuntimeError("first connection failed")

            def close(self) -> None:
                pass

        class _StoppingPubSub:
            def __init__(self, stop: _Stop) -> None:
                self._stop = stop

            def subscribe(self, _channel: str) -> None:
                pass

            def listen(self):
                self._stop.stopped = True
                return iter(())

            def close(self) -> None:
                pass

        class _Client:
            def __init__(self, pubsub) -> None:
                self._pubsub = pubsub

            def pubsub(self, ignore_subscribe_messages: bool = True):
                return self._pubsub

            def close(self) -> None:
                pass

        stop = _Stop()
        bus._stop = stop
        clients = [_Client(_FailingPubSub()), _Client(_StoppingPubSub(stop))]

        with patch(
            "app.services.visualization_service.get_redis_client",
            side_effect=clients,
        ) as get_client:
            bus._listen_loop()

        self.assertEqual(get_client.call_count, 2)


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
