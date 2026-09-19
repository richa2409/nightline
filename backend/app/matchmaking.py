"""
Matchmaking engine.

Design:
1. Every user's free-text "interests" blurb is vectorised with TF-IDF.
   This is a lightweight, dependency-free "AI" step that runs fully offline
   (no external API calls, no API key, no cost) — good for a demo/interview,
   and swappable for a transformer embedding model (see NOTE below) with
   zero changes to the matching algorithm itself.
2. Candidates are ranked by cosine similarity between vectors.
3. A Redis-backed queue holds users currently waiting for a partner, so the
   match step is O(n) over currently-waiting users, not the whole user table.

NOTE (interview talking point): swapping TF-IDF for a real embedding model
(e.g. sentence-transformers or an Anthropic/OpenAI embeddings endpoint) only
requires changing `vectorize()` — the rest of the pipeline (Redis queue,
cosine ranking, threshold) is unchanged. That's the point of isolating it
behind one function.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

import numpy as np
import redis
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

QUEUE_KEY = "matchmaking:queue"  # Redis LIST of user_ids waiting
PROFILE_KEY_PREFIX = "matchmaking:profile:"  # Redis HASH per user_id -> interests_text
RESULT_KEY_PREFIX = "matchmaking:result:"  # Redis STRING per user_id -> pending room details
MATCH_LOCK_KEY = "matchmaking:lock"
MATCH_RESULT_TTL_SECONDS = 60 * 60


@dataclass
class Candidate:
    user_id: str
    score: float


@dataclass
class PendingMatch:
    room_id: str
    partner_id: str
    score: float


def _vectorize(corpus: list[str]) -> np.ndarray:
    """Turn a list of interest blurbs into TF-IDF vectors. Empty corpus -> empty array."""
    if not corpus or all(not c.strip() for c in corpus):
        return np.zeros((len(corpus), 1))
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(corpus)
    return matrix.toarray()


def enqueue_user(user_id: str, interests_text: str) -> None:
    """Add a user to the waiting queue with their interest profile cached in Redis."""
    # A user who explicitly starts a new search should not be sent back to an
    # old room whose result they never opened.
    redis_client.delete(f"{RESULT_KEY_PREFIX}{user_id}")
    redis_client.hset(f"{PROFILE_KEY_PREFIX}{user_id}", mapping={"interests": interests_text or ""})
    redis_client.lrem(QUEUE_KEY, 0, user_id)  # avoid duplicate entries
    redis_client.rpush(QUEUE_KEY, user_id)


def dequeue_user(user_id: str) -> None:
    redis_client.lrem(QUEUE_KEY, 0, user_id)
    redis_client.delete(f"{PROFILE_KEY_PREFIX}{user_id}")


def save_pending_match(user_a_id: str, user_b_id: str, room_id: str, score: float) -> None:
    """Make the newly-created room visible to *both* participants.

    Matchmaking is poll-based, so the person who did not create the room needs
    a durable hand-off waiting for their next poll. The short TTL keeps Redis
    free of abandoned demo sessions.
    """
    pipeline = redis_client.pipeline()
    pipeline.setex(
        f"{RESULT_KEY_PREFIX}{user_a_id}",
        MATCH_RESULT_TTL_SECONDS,
        json.dumps({"room_id": room_id, "partner_id": user_b_id, "score": score}),
    )
    pipeline.setex(
        f"{RESULT_KEY_PREFIX}{user_b_id}",
        MATCH_RESULT_TTL_SECONDS,
        json.dumps({"room_id": room_id, "partner_id": user_a_id, "score": score}),
    )
    pipeline.execute()


def get_pending_match(user_id: str) -> PendingMatch | None:
    raw = redis_client.get(f"{RESULT_KEY_PREFIX}{user_id}")
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return PendingMatch(
            room_id=value["room_id"],
            partner_id=value["partner_id"],
            score=float(value["score"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        # Do not let one malformed/old cache entry strand a user in the queue.
        redis_client.delete(f"{RESULT_KEY_PREFIX}{user_id}")
        return None


def find_best_match(user_id: str, interests_text: str) -> Candidate | None:
    """
    Rank every other user currently in the queue by interest similarity
    to `user_id` and return the best one above the configured threshold.
    """
    waiting_ids = [uid for uid in redis_client.lrange(QUEUE_KEY, 0, -1) if uid != user_id]
    if not waiting_ids:
        return None

    profiles = [redis_client.hget(f"{PROFILE_KEY_PREFIX}{uid}", "interests") or "" for uid in waiting_ids]
    corpus = [interests_text or ""] + profiles
    vectors = _vectorize(corpus)

    if vectors.shape[1] == 1:  # degenerate case: no real text to compare, fall back to FIFO
        return Candidate(user_id=waiting_ids[0], score=0.0)

    similarities = cosine_similarity(vectors[0:1], vectors[1:])[0]
    best_idx = int(np.argmax(similarities))
    best_score = float(similarities[best_idx])

    if best_score < settings.MIN_SHARED_INTEREST_SCORE:
        # Nobody is a great fit yet — could still fall back to FIFO after a timeout
        # (handled by the caller / a background sweep job).
        return None

    return Candidate(user_id=waiting_ids[best_idx], score=best_score)
