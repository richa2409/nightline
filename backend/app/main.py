import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth_routes, chat_routes, match_routes, user_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anonmatch")

app = FastAPI(
    title=settings.APP_NAME,
    description="Anonymous chat with AI-driven interest matchmaking.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(user_routes.router)
app.include_router(match_routes.router)
app.include_router(chat_routes.router)


@app.on_event("startup")
def on_startup():
    # In production, use Alembic migrations instead of create_all.
    Base.metadata.create_all(bind=engine)
    logger.info("%s started in %s mode", settings.APP_NAME, settings.ENV)


@app.get("/health")
def health_check():
    """Used by Docker healthcheck + k8s readiness/liveness probes."""
    return {"status": "ok", "env": settings.ENV}
