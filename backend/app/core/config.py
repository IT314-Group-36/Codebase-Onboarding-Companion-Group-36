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

    # --- GitHub login (OAuth app) and sessions: used for private repos ---
    # Create the OAuth app at https://github.com/settings/developers; see backend/README.md.
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:5173/api/auth/github/callback"   # must match the OAuth app exactly
    frontend_url: str = "http://localhost:5173"          # where the browser is sent after login
    session_secret: str = ""                             # signs the session cookie (>= 32 chars)
    session_cookie_name: str = "session"
    session_ttl_seconds: int = 7 * 24 * 3600
    cookie_secure: bool = False                          # set true when served over https
    token_encryption_key: str = ""                       # Fernet key(s), comma-separated to rotate; encrypts stored GitHub tokens

    max_chunks: int = 5000
    max_file_bytes: int = 200_000

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret and self.session_secret and self.token_encryption_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
