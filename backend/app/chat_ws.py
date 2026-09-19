"""
Real-time chat over WebSockets.

A ConnectionManager keeps an in-memory map of room_id -> active sockets.
For a single backend instance this is sufficient; when scaling horizontally
(multiple backend pods behind a load balancer) you'd back this with Redis
Pub/Sub so a message from a socket on pod A reaches a socket on pod B.
That upgrade path is noted in the README as a deliberate simplification.
"""
from __future__ import annotations

import json
from typing import Dict, List

from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import ChatRoom, Message, User


class ConnectionManager:
    def __init__(self) -> None:
        self.active: Dict[str, List[WebSocket]] = {}

    async def connect(self, room_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.setdefault(room_id, []).append(websocket)

    def disconnect(self, room_id: str, websocket: WebSocket) -> None:
        if room_id in self.active and websocket in self.active[room_id]:
            self.active[room_id].remove(websocket)
            if not self.active[room_id]:
                del self.active[room_id]

    async def broadcast(self, room_id: str, payload: dict) -> None:
        for socket in self.active.get(room_id, []):
            await socket.send_json(payload)


manager = ConnectionManager()


def _authenticate(token: str) -> User | None:
    db: Session = SessionLocal()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user = db.query(User).filter(User.id == payload.get("sub")).first()
        return user
    except JWTError:
        return None
    finally:
        db.close()


async def chat_endpoint(websocket: WebSocket, room_id: str, token: str) -> None:
    user = _authenticate(token)
    if user is None:
        await websocket.close(code=4401)  # custom code: unauthorized
        return

    db: Session = SessionLocal()
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if room is None or user.id not in (room.user_a_id, room.user_b_id):
        db.close()
        await websocket.close(code=4403)  # forbidden: not your room
        return

    await manager.connect(room_id, websocket)
    await manager.broadcast(room_id, {
        "type": "system",
        "content": f"{user.anon_handle} joined the chat.",
    })

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            content = data.get("content", "").strip()
            if not content:
                continue

            msg = Message(room_id=room_id, sender_id=user.id, content=content)
            db.add(msg)
            db.commit()
            db.refresh(msg)

            await manager.broadcast(room_id, {
                "type": "message",
                "sender_handle": user.anon_handle,
                "content": content,
                "created_at": msg.created_at.isoformat(),
            })
    except WebSocketDisconnect:
        manager.disconnect(room_id, websocket)
        await manager.broadcast(room_id, {
            "type": "system",
            "content": f"{user.anon_handle} left the chat.",
        })
    finally:
        db.close()
