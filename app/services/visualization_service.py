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
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=max(1, settings.visualization_connection_queue_size)
        )
        writer_task = asyncio.create_task(self._writer_loop(websocket, queue))
        self._connections[websocket] = {"queue": queue, "writer_task": writer_task}
        self.send_one(
            websocket,
            {
                "type": "scene.snapshot",
                "payload": {
                    "events": self._recent_events[-50:],
                    "agents": agents or [],
                },
                "created_at": datetime.utcnow().isoformat(),
            },
        )

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
        await self._send_many_to_all([message], exclude=exclude)

    async def _send_many_to_all(
        self,
        messages: list[dict[str, Any]],
        exclude: WebSocket | None = None,
    ) -> None:
        disconnected: list[WebSocket] = []
        for websocket in list(self._connections):
            if websocket is exclude:
                continue
            if not self.send_many(websocket, messages):
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)

    def send_one(self, websocket: WebSocket, message: dict[str, Any]) -> bool:
        return self.send_many(websocket, [message])

    def send_many(self, websocket: WebSocket, messages: list[dict[str, Any]]) -> bool:
        if not messages:
            return True
        state = self._connections.get(websocket)
        if state is None:
            return False
        queue: asyncio.Queue[dict[str, Any]] = state["queue"]
        remaining = queue.maxsize - queue.qsize()
        if remaining < len(messages):
            return False
        for message in messages:
            queue.put_nowait(message)
        return True

    def _filter_new_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [message for message in messages if self._remember_message(message)]

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Persist to recent events (snapshot replay buffer) + push to all clients."""
        await self.broadcast_many([message])

    async def broadcast_many(self, messages: list[dict[str, Any]]) -> None:
        """Persist to recent events + push an ordered batch to all clients."""
        new_messages = self._filter_new_messages(messages)
        if not new_messages:
            return
        self._recent_events.extend(new_messages)
        self._recent_events = self._recent_events[-100:]
        await self._send_many_to_all(new_messages)

    async def broadcast_others(
        self, exclude: WebSocket, message: dict[str, Any]
    ) -> None:
        """Push to all clients except one, without persisting (transient presence)."""
        await self.broadcast_many_others(exclude, [message])

    async def broadcast_many_others(
        self, exclude: WebSocket, messages: list[dict[str, Any]]
    ) -> None:
        """Push an ordered batch to all clients except one, without replay."""
        new_messages = self._filter_new_messages(messages)
        if not new_messages:
            return
        await self._send_many_to_all(new_messages, exclude=exclude)

    async def broadcast_transient(self, message: dict[str, Any]) -> None:
        """Push to all clients without persisting (transient presence notifications).

        Used for come-online / go-offline signals so they don't pollute the snapshot
        replay buffer (replaying a stale leave_scene would wrongly remove avatars).
        """
        await self.broadcast_many_transient([message])

    async def broadcast_many_transient(self, messages: list[dict[str, Any]]) -> None:
        new_messages = self._filter_new_messages(messages)
        if not new_messages:
            return
        await self._send_many_to_all(new_messages)

    def broadcast_from_sync(self, message: dict[str, Any]) -> None:
        self.broadcast_many_from_sync([message])

    def broadcast_many_from_sync(self, messages: list[dict[str, Any]]) -> None:
        try:
            anyio.from_thread.run(self.broadcast_many, messages)
        except RuntimeError:
            pass

    def broadcast_transient_from_sync(self, message: dict[str, Any]) -> None:
        self.broadcast_many_transient_from_sync([message])

    def broadcast_many_transient_from_sync(self, messages: list[dict[str, Any]]) -> None:
        try:
            anyio.from_thread.run(self.broadcast_many_transient, messages)
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
        return (await self.publish_many([message], replay=replay, exclude=exclude))[0]

    async def publish_many(
        self,
        messages: list[dict[str, Any]],
        *,
        replay: bool = True,
        exclude: WebSocket | None = None,
    ) -> list[dict[str, Any]]:
        enriched = [_with_bus_metadata(message) for message in messages]
        if not enriched:
            return []
        if replay:
            await self.hub.broadcast_many(enriched)
        elif exclude is not None:
            await self.hub.broadcast_many_others(exclude, enriched)
        else:
            await self.hub.broadcast_many_transient(enriched)
        self._publish_many_to_redis(enriched, replay=replay)
        return enriched

    def publish_from_sync(self, message: dict[str, Any], *, replay: bool = True) -> dict[str, Any]:
        return self.publish_many_from_sync([message], replay=replay)[0]

    def publish_many_from_sync(
        self,
        messages: list[dict[str, Any]],
        *,
        replay: bool = True,
    ) -> list[dict[str, Any]]:
        enriched = [_with_bus_metadata(message) for message in messages]
        if not enriched:
            return []
        if replay:
            self.hub.broadcast_many_from_sync(enriched)
        else:
            self.hub.broadcast_many_transient_from_sync(enriched)
        self._publish_many_to_redis(enriched, replay=replay)
        return enriched

    def _publish_to_redis(self, message: dict[str, Any], *, replay: bool) -> None:
        self._publish_to_redis_envelope({"origin_id": self.origin_id, "replay": replay, "message": message})

    def _publish_many_to_redis(self, messages: list[dict[str, Any]], *, replay: bool) -> None:
        if not messages:
            return
        if len(messages) == 1:
            self._publish_to_redis(messages[0], replay=replay)
            return
        self._publish_to_redis_envelope(
            {
                "origin_id": self.origin_id,
                "replay": replay,
                "messages": messages,
            }
        )

    def _publish_to_redis_envelope(self, envelope: dict[str, Any]) -> None:
        if settings.use_fakeredis:
            return
        try:
            if self._publisher is None:
                self._publisher = get_redis_client(decode_responses=True)
            self._publisher.publish(
                settings.visualization_redis_channel,
                encode_json(envelope),
            )
        except Exception:
            self._publisher = None
            logger.warning("Failed to publish visualization event to Redis", exc_info=True)

    def _listen_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            redis_client = None
            pubsub = None
            try:
                redis_client = get_redis_client(decode_responses=True)
                self._redis = redis_client
                pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(settings.visualization_redis_channel)
                backoff = 1.0
                for item in pubsub.listen():
                    if self._stop.is_set():
                        break
                    if item.get("type") != "message":
                        continue
                    self._handle_redis_message(str(item.get("data") or ""))
            except Exception:
                if not self._stop.is_set():
                    logger.warning("Visualization Redis Pub/Sub listener stopped", exc_info=True)
            finally:
                if pubsub is not None:
                    try:
                        pubsub.close()
                    except Exception:
                        pass
                if redis_client is not None:
                    try:
                        redis_client.close()
                    except Exception:
                        pass
                if self._redis is redis_client:
                    self._redis = None
            if not self._stop.is_set():
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)

    def _handle_redis_message(self, raw: str) -> None:
        try:
            envelope = json.loads(raw)
            if isinstance(envelope.get("messages"), list):
                messages = envelope["messages"]
            else:
                messages = [envelope["message"]]
            replay = bool(envelope.get("replay", True))
        except Exception:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        coroutine = (
            self.hub.broadcast_many(messages)
            if replay
            else self.hub.broadcast_many_transient(messages)
        )
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
    return visualization_event_bus.publish_many_from_sync(messages, replay=True)


def broadcast_visualization_message(
    message: dict[str, Any],
    *,
    replay: bool = True,
) -> dict[str, Any]:
    return visualization_event_bus.publish_from_sync(message, replay=replay)
