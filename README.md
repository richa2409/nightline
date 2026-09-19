# Nightline — Anonymous Chat with AI Matchmaking

Talk to a stranger who's into the same things you are. You sign up with an
email (so you can come back), but everyone you meet only ever sees an
auto-generated handle like `Silent Falcon #482` — never your email, never a
real name.

This repo is built to demonstrate three things end-to-end: a real Python
backend, a full DevOps pipeline, and a practical (not gimmicky) use of AI —
in this case, AI-driven interest matchmaking.

---

## How it works

1. **Sign up** with an email/password and a free-text blurb about your interests.
2. **Join the queue.** Your interest blurb is vectorised (TF-IDF) and cached in Redis.
3. **Matchmaking.** The backend ranks everyone currently waiting by cosine
   similarity to your interest vector and pairs you with your best-scoring
   match above a configurable threshold.
4. **Chat.** A private room is created and both users connect over a
   WebSocket for real-time messaging. Messages are persisted so either side
   can reload history.
5. **End the chat** whenever you want — the room is timestamped closed, no
   ongoing relationship or contact info is exchanged.

---

## Architecture

```
┌────────────┐      ┌──────────────┐      ┌─────────────┐
│  Frontend  │◄────►│    Nginx     │◄────►│   FastAPI   │
│  (static)  │      │ (reverse     │      │   backend   │
└────────────┘      │  proxy +     │      └──────┬──────┘
                     │  WS upgrade) │             │
                     └──────────────┘      ┌──────┴──────┐
                                            │             │
                                     ┌──────▼─────┐ ┌─────▼─────┐
                                     │ PostgreSQL │ │   Redis   │
                                     │ (users,    │ │ (matchmaking
                                     │  messages) │ │  queue)   │
                                     └────────────┘ └───────────┘
```

- **FastAPI** for the backend — async, typed, auto-generated OpenAPI docs at `/docs`.
- **PostgreSQL** for durable data: accounts, chat rooms, message history.
- **Redis** for the ephemeral matchmaking queue — fast reads/writes, no need
  to hit Postgres every couple of seconds while someone's waiting.
- **WebSockets** for real-time chat, with a small in-memory connection
  manager (see "Known simplifications" below for how this scales further).
- **Nginx** as a reverse proxy in front of both the static frontend and the
  API, handling the WebSocket `Upgrade` header.
- **Docker Compose** to run the whole stack locally or on a single VM.
- **GitHub Actions** for CI/CD: lint → test → build image → push to GHCR → deploy over SSH.
- **Kubernetes manifests** (`deploy/k8s/`) as the scale-out path: a
  Deployment with readiness/liveness probes and an HPA that autoscales on CPU.

---

## The "AI" part, honestly explained

The matchmaking engine (`backend/app/matchmaking.py`) vectorises each
person's interest blurb with **TF-IDF** and ranks candidates by **cosine
similarity**. This is a real, working NLP technique — not a toy — and it
runs entirely offline with no API key and no per-request cost, which makes
the whole project runnable and testable without any external dependency.

It's also deliberately built so the "AI" is swappable: `vectorize()` is the
only place that would change if you wanted to plug in transformer sentence
embeddings (`sentence-transformers`) or an API-based embedding model — the
Redis queue, the cosine ranking, and the similarity threshold are all
unchanged. That's a good story to tell in an interview: you understand
*where* the ML boundary should sit in a system, not just how to call an API.

---

## Running it locally

```bash
cp .env.example .env        # edit SECRET_KEY etc.
docker compose up --build
```

The first build downloads the container images and Python dependencies. Keep
the terminal running, then open the app in a browser. To demo matching, open a
second browser profile (or an incognito window), create another account with
overlapping interests, and join the queue from both sessions.

- App: http://localhost:8080
- API docs (Swagger): http://localhost:8080/api/docs
- Health check: http://localhost:8080/api/health

## Running the backend tests

```bash
cd backend
pip install -r requirements.txt
pytest -v
```

---

## CI/CD pipeline (`.github/workflows/ci-cd.yml`)

On every push to `main`:
1. **Lint** with `ruff`.
2. **Test** with `pytest` (uses SQLite in-memory + a real Redis service
   container, so it needs no external infrastructure).
3. **Build** a multi-stage Docker image (builder stage compiles
   dependencies, runtime stage is slim and runs as a non-root user).
4. **Push** the image to GitHub Container Registry, tagged both `latest`
   and with the commit SHA (so any deploy is traceable back to an exact commit).
5. **Deploy** over SSH to a VM running docker-compose (swap this step for
   `kubectl apply -f deploy/k8s/` if deploying to a cluster instead).

Pull requests run steps 1–2 only (no deploy), so broken code never reaches `main`.

---

## Known simplifications (worth mentioning if asked)

These are deliberate, scoped-for-a-demo choices, not oversights — good to be
upfront about in an interview:

- **WebSocket connections are held in-process.** Fine for one backend
  instance; horizontally scaling to N pods needs Redis Pub/Sub (or NATS) so
  a message sent to a socket on pod A reaches a socket on pod B. The queue
  logic already lives in Redis, so this is a natural next step, not a rewrite.
- **Matchmaking is poll-based** (`POST /match/poll` every ~2.5s) rather than
  push-based. A production version would push a match over a WebSocket the
  moment it's found, cutting both latency and request volume.
- **TF-IDF, not embeddings.** Chosen so the project runs with zero external
  API keys and zero inference cost — see "The AI part" above for the upgrade path.
- **Alembic is a dependency but migrations aren't included** —
  `Base.metadata.create_all()` runs on startup for demo simplicity. A real
  deployment should use versioned Alembic migrations instead.

---

## Project layout

```
anon-chat-ai/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app + startup
│   │   ├── config.py        # env-driven settings
│   │   ├── database.py      # SQLAlchemy engine/session
│   │   ├── models.py        # User, ChatRoom, Message, MatchRequest
│   │   ├── schemas.py       # Pydantic request/response models
│   │   ├── auth.py          # JWT + bcrypt + anon handle generator
│   │   ├── matchmaking.py   # TF-IDF + cosine similarity + Redis queue
│   │   ├── chat_ws.py       # WebSocket connection manager
│   │   └── routers/         # auth / users / match / chat endpoints
│   ├── tests/                # pytest suite (run in CI)
│   ├── Dockerfile            # multi-stage, non-root, healthcheck
│   └── requirements.txt
├── frontend/                 # static HTML/CSS/JS, no build step
├── nginx/nginx.conf          # reverse proxy + WS upgrade
├── docker-compose.yml
├── .github/workflows/ci-cd.yml
└── deploy/
    ├── deploy.sh              # single-VM deploy script
    └── k8s/api-deployment.yaml # Deployment + Service + HPA
```
