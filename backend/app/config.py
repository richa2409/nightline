"""
Centralised app configuration.
All secrets/config are pulled from environment variables (12-factor style),
so the exact same image runs in dev / staging / prod with different .env files.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "AnonMatch"
    ENV: str = "development"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = "change-me-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Database
    DATABASE_URL: str = "postgresql://anon_user:anon_pass@db:5432/anon_chat"

    # Redis (used for presence, matchmaking queue, pub/sub between workers)
    REDIS_URL: str = "redis://redis:6379/0"

    # Matchmaking
    MIN_SHARED_INTEREST_SCORE: float = 0.15  # cosine-similarity floor to be considered a match

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:8080", "*"]


settings = Settings()
