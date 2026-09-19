import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

# Nginx strips `/api` in the local Compose stack. Render serves the SPA from
# this same FastAPI process, so retain the prefixed aliases there as well.
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_routes.router)
api_router.include_router(user_routes.router)
api_router.include_router(match_routes.router)
api_router.include_router(chat_routes.router)
app.include_router(api_router)


@app.on_event("startup")
def on_startup():
    # In production, use Alembic migrations instead of create_all.
    Base.metadata.create_all(bind=engine)
    logger.info("%s started in %s mode", settings.APP_NAME, settings.ENV)


@app.get("/health")
def health_check():
    """Used by Docker healthcheck + k8s readiness/liveness probes."""
    return {"status": "ok", "env": settings.ENV}


# The local Compose stack serves the frontend through Nginx. The Render image
# also copies these assets so one public web service can host the SPA and API.
frontend_dir = Path("/app/frontend")
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
