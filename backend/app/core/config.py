"""
Core Configuration — Sahayak AI Backend
=========================================
Pydantic v2 BaseSettings — type-safe, env-driven, cached singleton.
All secrets loaded from environment variables / .env file.
"""

import json
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────
    APP_NAME: str = Field(default="Sahayak AI")
    APP_VERSION: str = Field(default="0.1.0")
    APP_ENV: str = Field(default="development")  # development | staging | production

    # ── Security ──────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(default="change-me-in-production-use-a-long-random-string")
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://sahayak:sahayak_password@localhost:5432/sahayak_db"
    )
    # Override SQL echo — defaults to True in dev, False in prod
    DATABASE_ECHO: bool = Field(default=False)
    # Connection pool
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_TIMEOUT: int = Field(default=30)    # seconds to wait for a free connection
    DB_POOL_RECYCLE: int = Field(default=1800)  # recycle connections after 30 min

    # ── CORS ──────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # ── Logging ───────────────────────────────────────────────────────────
    LOG_LEVEL: str = Field(default="INFO")

    # ── Translation Infrastructure ────────────────────────────────────────
    TRANSLATION_PROVIDER: str = Field(default="indictrans2")
    TRANSLATION_MODEL_NAME: str = Field(default="prajdabre/rotary-indictrans2-en-indic-dist-200M")
    TRANSLATION_BATCH_SIZE: int = Field(default=8)
    TRANSLATION_DEVICE: str = Field(default="auto")
    MODEL_CACHE_DIR: str = Field(default="models/indictrans2")
    TRANSLATION_MAX_RETRIES: int = Field(default=3)

    # ── AI Chat (RAG Assistant) ──────────────────────────────────────────
    GROQ_API_KEY: str = Field(default="")
    GROQ_CHAT_MODEL: str = Field(default="openai/gpt-oss-20b")
    GROQ_STT_MODEL: str = Field(default="whisper-large-v3")
    CHAT_MAX_AUDIO_UPLOAD_MB: int = Field(default=15)

    # ── Computed properties ───────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"

    @property
    def should_echo_sql(self) -> bool:
        """Echo SQL in dev unless DATABASE_ECHO explicitly set to False."""
        if self.DATABASE_ECHO:
            return True
        return self.is_development


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Cached settings singleton — imported everywhere as:
        from app.core.config import settings
    """
    return Settings()


settings = get_settings()
