from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.matchmaking import (
    MATCH_LOCK_KEY,
    dequeue_user,
    enqueue_user,
    find_best_match,
    get_pending_match,
    redis_client,
    save_pending_match,
)
from app.models import ChatRoom, User
from app.schemas import MatchResult

router = APIRouter(prefix="/match", tags=["matchmaking"])


@router.post("/join")
def join_queue(current_user: User = Depends(get_current_user)):
    """Put the current user into the matchmaking queue."""
    enqueue_user(current_user.id, current_user.interests_text)
    return {"status": "queued"}


@router.post("/leave")
def leave_queue(current_user: User = Depends(get_current_user)):
    dequeue_user(current_user.id)
    return {"status": "left_queue"}


@router.post("/poll", response_model=MatchResult | dict)
def poll_for_match(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Client polls this every couple of seconds while waiting (or you can
    replace with a Redis pub/sub + WebSocket push — see README for the
    production-grade alternative).
    """
    def result_for_pending_match():
        pending = get_pending_match(current_user.id)
        if not pending:
            return None
        partner = db.query(User).filter(User.id == pending.partner_id).first()
        if not partner:
            return None
        return MatchResult(
            room_id=pending.room_id,
            partner_handle=partner.anon_handle,
            match_score=round(pending.score, 3),
        )

    # Fast path for the participant whose partner created the room first.
    pending_result = result_for_pending_match()
    if pending_result:
        return pending_result

    # Selecting a partner and removing both people from the queue must be one
    # critical section; otherwise two simultaneous polls can create duplicates.
    lock = redis_client.lock(MATCH_LOCK_KEY, timeout=5, blocking_timeout=1)
    try:
        if not lock.acquire():
            return {"status": "waiting"}
        # Another poll may have completed a match while this request waited.
        pending_result = result_for_pending_match()
        if pending_result:
            return pending_result

        candidate = find_best_match(current_user.id, current_user.interests_text)
        if not candidate:
            return {"status": "waiting"}

        partner = db.query(User).filter(User.id == candidate.user_id).first()
        if not partner:
            dequeue_user(candidate.user_id)
            return {"status": "waiting"}

        room = ChatRoom(
            user_a_id=current_user.id,
            user_b_id=partner.id,
            match_score=candidate.score,
        )
        db.add(room)
        db.commit()
        db.refresh(room)

        save_pending_match(current_user.id, partner.id, room.id, candidate.score)
        dequeue_user(current_user.id)
        dequeue_user(partner.id)

        return MatchResult(
            room_id=room.id,
            partner_handle=partner.anon_handle,
            match_score=round(candidate.score, 3),
        )
    finally:
        if lock.owned():
            lock.release()
