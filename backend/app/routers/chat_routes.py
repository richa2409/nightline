import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.chat_ws import chat_endpoint
from app.database import get_db
from app.models import ChatRoom, Message, User
from app.schemas import MessageOut

router = APIRouter(tags=["chat"])


@router.websocket("/ws/chat/{room_id}")
async def websocket_chat(websocket: WebSocket, room_id: str, token: str):
    """Connect with: ws://host/ws/chat/{room_id}?token=<JWT>"""
    await chat_endpoint(websocket, room_id, token)


@router.get("/chat/{room_id}/history", response_model=list[MessageOut])
def get_history(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if room is None or current_user.id not in (room.user_a_id, room.user_b_id):
        raise HTTPException(status_code=403, detail="Not your room")

    messages = db.query(Message).filter(Message.room_id == room_id).order_by(Message.created_at).all()
    return [
        MessageOut(
            id=m.id,
            sender_handle=m.sender.anon_handle,
            content=m.content,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.post("/chat/{room_id}/end")
def end_chat(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if room is None or current_user.id not in (room.user_a_id, room.user_b_id):
        raise HTTPException(status_code=403, detail="Not your room")
    room.ended_at = dt.datetime.utcnow()
    db.commit()
    return {"status": "ended"}
