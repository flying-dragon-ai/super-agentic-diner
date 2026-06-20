from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from typing import Any

import anyio
from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.db.models import VisualizationEvent

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


class VisualizationHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._recent_events: list[dict[str, Any]] = []
        # Logged-in web customers with a live WS connection (websocket -> agent_id).
        # Only web users land here — Skill/CLI scripts can't hold a WS, so they rely
        # on the agent.last_seen_at heartbeat window in the snapshot builder instead.
        self._ws_agent: dict[WebSocket, int] = {}

    async def connect(
        self,
        websocket: WebSocket,
        agents: list[dict[str, Any]] | None = None,
    ) -> None:
        await websocket.accept()
        self._connections.add(websocket)
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

    def register_ws_presence(self, websocket: WebSocket, agent_id: int) -> None:
        """Mark a websocket as carrying a logged-in web customer agent."""
        self._ws_agent[websocket] = agent_id

    def online_ws_agent_ids(self) -> set[int]:
        """Customer agent_ids that currently have a live web WS connection."""
        return set(self._ws_agent.values())

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        self._ws_agent.pop(websocket, None)

    async def _send_to_all(
        self,
        message: dict[str, Any],
        exclude: WebSocket | None = None,
    ) -> None:
        disconnected: list[WebSocket] = []
        for websocket in list(self._connections):
            if websocket is exclude:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Persist to recent events (snapshot replay buffer) + push to all clients."""
        self._recent_events.append(message)
        self._recent_events = self._recent_events[-100:]
        await self._send_to_all(message)

    async def broadcast_others(
        self, exclude: WebSocket, message: dict[str, Any]
    ) -> None:
        """Push to all clients except one, without persisting (transient presence)."""
        await self._send_to_all(message, exclude=exclude)

    async def broadcast_transient(self, message: dict[str, Any]) -> None:
        """Push to all clients without persisting (transient presence notifications).

        Used for come-online / go-offline signals so they don't pollute the snapshot
        replay buffer (replaying a stale leave_scene would wrongly remove avatars).
        """
        await self._send_to_all(message)

    def broadcast_from_sync(self, message: dict[str, Any]) -> None:
        try:
            anyio.from_thread.run(self.broadcast, message)
        except RuntimeError:
            pass


visualization_hub = VisualizationHub()
