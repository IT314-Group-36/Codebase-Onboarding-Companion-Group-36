from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]      # backend/ (holds .env, alembic.ini, ...)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://onboard:onboard@localhost:5432/onboard"
    redis_url: str = "redis://localhost:6379"
    cors_origins: list[str] = ["http://localhost:5173"]
    work_dir: str = "/tmp/onboarding_work"
    allow_local_repos: bool = False          # tests / local demos only

    # LLM via LangChain: "<provider>:<model>". Examples: google_genai:gemini-3.6-flash, openai:gpt-5, anthropic:<model>
    llm_model: str = "google_genai:gemini-3.6-flash"   # check availability on your free tier in AI Studio
    llm_api_key: str = Field("", validation_alias=AliasChoices("LLM_API_KEY", "GOOGLE_API_KEY"))
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 4
    llm_min_interval_seconds: float = 4.0    # spacing between calls (LangChain rate limiter) for free-tier limits

    embed_backend: str = "fastembed"         # fastembed | hash (hash = tests only)
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384                     # must match the migrated vector column

    max_chunks: int = 5000
    max_file_bytes: int = 200_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
