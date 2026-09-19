import uuid
import datetime as dt

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, JSON, Float
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# Plain String(36) primary keys (holding UUID text) rather than the
# Postgres-only UUID type: this keeps the same models working against
# SQLite in tests/CI and Postgres in prod, with no dialect-specific code.
def UUID_COL(*args, **kwargs):
    return Column(String(36), *args, **kwargs)


class User(Base):
    """
    A real account (email + hashed password) exists ONLY for auth/persistence.
    Nobody ever sees another user's email or real name — every user is shown
    to others only via their `anon_handle` (e.g. "Silent Falcon #482").
    """
    __tablename__ = "users"

    id = UUID_COL(primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    anon_handle = Column(String, unique=True, nullable=False)
    interests_text = Column(Text, default="")          # raw free-text interests
    interest_vector = Column(JSON, nullable=True)  # cached TF-IDF/embedding vector (list[float])
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    sent_messages = relationship("Message", back_populates="sender")


class MatchRequest(Base):
    """A user sitting in the matchmaking queue looking for a partner."""
    __tablename__ = "match_requests"

    id = UUID_COL(primary_key=True, default=gen_uuid)
    user_id = UUID_COL(ForeignKey("users.id"), nullable=False)
    status = Column(String, default="queued")  # queued | matched | cancelled
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class ChatRoom(Base):
    """A 1:1 anonymous room created once two users are matched."""
    __tablename__ = "chat_rooms"

    id = UUID_COL(primary_key=True, default=gen_uuid)
    user_a_id = UUID_COL(ForeignKey("users.id"), nullable=False)
    user_b_id = UUID_COL(ForeignKey("users.id"), nullable=False)
    match_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

    messages = relationship("Message", back_populates="room")


class Message(Base):
    __tablename__ = "messages"

    id = UUID_COL(primary_key=True, default=gen_uuid)
    room_id = UUID_COL(ForeignKey("chat_rooms.id"), nullable=False)
    sender_id = UUID_COL(ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    room = relationship("ChatRoom", back_populates="messages")
    sender = relationship("User", back_populates="sent_messages")
