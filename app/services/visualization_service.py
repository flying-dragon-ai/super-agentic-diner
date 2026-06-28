from __future__ import annotations

import asyncio
from collections import deque
import hashlib
import json
import logging
import secrets
import threading
import uuid
from datetime import datetime
from typing import Any

import anyio
from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import VisualizationEvent
from app.memory._redis_client import get_redis_client

logger = logging.getLogger(__name__)

VALID_AGENT_ROLES = {"customer", "waiter", "cashier", "barista", "manager"}
VALID_AGENT_ACTIONS = {
    "enter_scene",
    "walk_to_counter",
    "walk_to_table",
    "take_order",
    "prepare_coffee",
    "deliver_order",
    "show_message",
    "leave_scene",
    "error",
}


def generate_agent_token() -> str:
    return "pa_" + secrets.token_urlsafe(32)


def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def make_sprite_seed() -> int:
    return secrets.randbelow(900_000) + 100_000


def encode_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def decode_json(text: str | None, fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def event_to_message(event: VisualizationEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "type": event.event_type,
        "agent_id": event.agent_id,
        "payload": decode_json(event.payload_json, {}),
        "correlation_id": event.correlation_id,
        "created_at": event.created_at.isoformat(),
    }


def _event_to_message_key(message: dict[str, Any]) -> str | None:
    message_id = message.get("message_id")
    if message_id:
        return f"message:{message_id}"
    event_id = message.get("event_id")
    if event_id is not None:
        return f"event:{event_id}"
    return None


def _with_bus_metadata(message: dict[str, Any]) -> dict[str, Any]:
    if message.get("message_id"):
        return message
    enriched = dict(message)
    enriched["message_id"] = uuid.uuid4().hex
    return enriched


def create_visualization_event(
    db: Session,
    event_type: str,
    payload: dict[str, Any],
    agent_id: int | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    event = VisualizationEvent(
        agent_id=agent_id,
        event_type=event_type,
        payload_json=encode_json(payload),
        correlation_id=correlation_id,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event_to_message(event)


def create_visualization_events(
    db: Session,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Persist multiple visualization events with one commit.

    Each item accepts ``event_type``, ``payload``, optional ``agent_id`` and
    optional ``correlation_id``. The returned messages preserve input order.
    """
    rows: list[VisualizationEvent] = []
    for item in events:
        row = VisualizationEvent(
            agent_id=item.get("agent_id"),
            event_type=item["event_type"],
            payload_json=encode_json(item.get("payload") or {}),
            correlation_id=item.get("correlation_id"),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return [event_to_message(row) for row in rows]


class VisualizationHub:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, dict[str, Any]] = {}
        self._recent_events: list[dict[str, Any]] = []
        self._seen_message_keys: set[str] = set()
        self._seen_message_order: deque[str] = deque(maxlen=1000)
        # Logged-in web customers with a live WS connection (websocket -> agent_id).
        # Only web users land here — Skill/CLI scripts can't hold a WS, so they rely
        # on the agent.last_seen_at heartbeat window in the snapshot builder instead.
        self._ws_agent: dict[WebSocket, int] = {}

    def _remember_message(self, message: dict[str, Any]) -> bool:
        key = _event_to_message_key(message)
        if key is None:
            return True
        if key in self._seen_message_keys:
            return False
        if len(self._seen_message_order) == self._seen_message_order.maxlen:
            old = self._seen_message_order.popleft()
            self._seen_message_keys.discard(old)
        self._seen_message_order.append(key)
        self._seen_message_keys.add(key)
        return True

    async def connect(
        self,
        websocket: WebSocket,
        agents: list[dict[str, Any]] | None = None,
    ) -> None:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "scene.snapshot",
                "payload": {
                    "events": self._recent_events[-50:],
                    "agents": agents or [],
                },
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=max(1, settings.visualization_connection_queue_size)
        )
        writer_task = asyncio.create_task(self._writer_loop(websocket, queue))
        self._connections[websocket] = {"queue": queue, "writer_task": writer_task}

    async def _writer_loop(
        self,
        websocket: WebSocket,
        queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        timeout = max(0.05, settings.visualization_send_timeout_ms / 1000)
        try:
            while True:
                message = await queue.get()
                await asyncio.wait_for(websocket.send_json(message), timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.disconnect(websocket)

    def register_ws_presence(self, websocket: WebSocket, agent_id: int) -> None:
        """Mark a websocket as carrying a logged-in web customer agent."""
        self._ws_agent[websocket] = agent_id

    def online_ws_agent_ids(self) -> set[int]:
        """Customer agent_ids that currently have a live web WS connection."""
        return set(self._ws_agent.values())

    def disconnect(self, websocket: WebSocket) -> None:
        state = self._connections.pop(websocket, None)
        if state:
            task = state.get("writer_task")
            if task and task is not asyncio.current_task():
                task.cancel()
        self._ws_agent.pop(websocket, None)

    async def _send_to_all(
        self,
        message: dict[str, Any],
        exclude: WebSocket | None = None,
    ) -> None:
        disconnected: list[WebSocket] = []
        for websocket, state in list(self._connections.items()):
            if websocket is exclude:
                continue
            if not self.send_one(websocket, message):
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)

    def send_one(self, websocket: WebSocket, message: dict[str, Any]) -> bool:
        state = self._connections.get(websocket)
        if state is None:
            return False
        queue: asyncio.Queue[dict[str, Any]] = state["queue"]
        if queue.full():
            return False
        queue.put_nowait(message)
        return True

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Persist to recent events (snapshot replay buffer) + push to all clients."""
        if not self._remember_message(message):
            return
        self._recent_events.append(message)
        self._recent_events = self._recent_events[-100:]
        await self._send_to_all(message)

    async def broadcast_others(
        self, exclude: WebSocket, message: dict[str, Any]
    ) -> None:
        """Push to all clients except one, without persisting (transient presence)."""
        if not self._remember_message(message):
            return
        await self._send_to_all(message, exclude=exclude)

    async def broadcast_transient(self, message: dict[str, Any]) -> None:
        """Push to all clients without persisting (transient presence notifications).

        Used for come-online / go-offline signals so they don't pollute the snapshot
        replay buffer (replaying a stale leave_scene would wrongly remove avatars).
        """
        if not self._remember_message(message):
            return
        await self._send_to_all(message)

    def broadcast_from_sync(self, message: dict[str, Any]) -> None:
        try:
            anyio.from_thread.run(self.broadcast, message)
        except RuntimeError:
            pass

    def broadcast_transient_from_sync(self, message: dict[str, Any]) -> None:
        try:
            anyio.from_thread.run(self.broadcast_transient, message)
        except RuntimeError:
            pass


visualization_hub = VisualizationHub()


class VisualizationEventBus:
    """Redis-backed fan-out for visualization events across uvicorn workers."""

    def __init__(self, hub: VisualizationHub) -> None:
        self.hub = hub
        self.origin_id = uuid.uuid4().hex
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._redis = None
        self._publisher = None

    async def start(self) -> None:
        if settings.use_fakeredis:
            logger.info("Visualization Redis Pub/Sub disabled in fakeredis mode")
            return
        if self._thread and self._thread.is_alive():
            return
        self._loop = asyncio.get_running_loop()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="visualization-event-bus",
            daemon=True,
        )
        self._thread.start()

    async def stop(self) -> None:
        self._stop.set()
        redis_client = self._redis
        if redis_client is not None:
            try:
                redis_client.close()
            except Exception:
                pass
        publisher = self._publisher
        if publisher is not None:
            try:
                publisher.close()
            except Exception:
                pass

    async def publish(
        self,
        message: dict[str, Any],
        *,
        replay: bool = True,
        exclude: WebSocket | None = None,
    ) -> dict[str, Any]:
        enriched = _with_bus_metadata(message)
        if replay:
            await self.hub.broadcast(enriched)
        elif exclude is not None:
            await self.hub.broadcast_others(exclude, enriched)
        else:
            await self.hub.broadcast_transient(enriched)
        self._publish_to_redis(enriched, replay=replay)
        return enriched

    def publish_from_sync(self, message: dict[str, Any], *, replay: bool = True) -> dict[str, Any]:
        enriched = _with_bus_metadata(message)
        if replay:
            self.hub.broadcast_from_sync(enriched)
        else:
            self.hub.broadcast_transient_from_sync(enriched)
        self._publish_to_redis(enriched, replay=replay)
        return enriched

    def _publish_to_redis(self, message: dict[str, Any], *, replay: bool) -> None:
        if settings.use_fakeredis:
            return
        try:
            if self._publisher is None:
                self._publisher = get_redis_client(decode_responses=True)
            self._publisher.publish(
                settings.visualization_redis_channel,
                encode_json(
                    {
                        "origin_id": self.origin_id,
                        "replay": replay,
                        "message": message,
                    }
                ),
            )
        except Exception:
            self._publisher = None
            logger.warning("Failed to publish visualization event to Redis", exc_info=True)

    def _listen_loop(self) -> None:
        try:
            self._redis = get_redis_client(decode_responses=True)
            pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(settings.visualization_redis_channel)
            for item in pubsub.listen():
                if self._stop.is_set():
                    break
                if item.get("type") != "message":
                    continue
                self._handle_redis_message(str(item.get("data") or ""))
        except Exception:
            if not self._stop.is_set():
                logger.warning("Visualization Redis Pub/Sub listener stopped", exc_info=True)

    def _handle_redis_message(self, raw: str) -> None:
        try:
            envelope = json.loads(raw)
            message = envelope["message"]
            replay = bool(envelope.get("replay", True))
        except Exception:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        coroutine = self.hub.broadcast(message) if replay else self.hub.broadcast_transient(message)
        asyncio.run_coroutine_threadsafe(coroutine, loop)


visualization_event_bus = VisualizationEventBus(visualization_hub)


def publish_visualization_event(
    db: Session,
    event_type: str,
    payload: dict[str, Any],
    *,
    agent_id: int | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    message = create_visualization_event(
        db,
        event_type=event_type,
        payload=payload,
        agent_id=agent_id,
        correlation_id=correlation_id,
    )
    return visualization_event_bus.publish_from_sync(message, replay=True)


def publish_visualization_events(
    db: Session,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    messages = create_visualization_events(db, events)
    return [
        visualization_event_bus.publish_from_sync(message, replay=True)
        for message in messages
    ]


def broadcast_visualization_message(
    message: dict[str, Any],
    *,
    replay: bool = True,
) -> dict[str, Any]:
    return visualization_event_bus.publish_from_sync(message, replay=replay)
