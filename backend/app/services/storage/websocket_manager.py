from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from fastapi import WebSocket

from app.models import WebSocketMessage, now_utc


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[session_id].add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        self._connections[session_id].discard(websocket)

    async def send(self, websocket: WebSocket, session_id: str, message_type: str, payload: dict) -> None:
        message = WebSocketMessage(
            type=message_type,
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=session_id,
            timestamp=now_utc(),
            payload=payload,
        )
        await websocket.send_json(message.model_dump(mode="json"))

    async def broadcast(self, session_id: str, message_type: str, payload: dict) -> None:
        for websocket in list(self._connections.get(session_id, set())):
            try:
                await self.send(websocket, session_id, message_type, payload)
            except Exception:
                self.disconnect(session_id, websocket)

    async def broadcast_message(self, session_id: str, message: dict) -> None:
        """Broadcast a durable message without replacing its event identity."""
        for websocket in list(self._connections.get(session_id, set())):
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(session_id, websocket)
