from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]      # backend/ (holds .env, alembic.ini, ...)


def normalize_database_url(url: str) -> str:
    """Accept the URL exactly as a host gives it (Neon, Render, Heroku: `postgresql://` or `postgres://`) and turn it
    into the psycopg 3 form SQLAlchemy needs. Neon hosts also get `sslmode=require` if the URL does not set it."""
    url = url.strip()
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
            break
    parts = urlsplit(url)
    if parts.scheme == "postgresql+psycopg" and (parts.hostname or "").endswith("neon.tech") and "sslmode=" not in parts.query:
        query = f"{parts.query}&sslmode=require" if parts.query else "sslmode=require"
        url = urlunsplit(parts._replace(query=query))
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://onboard:onboard@localhost:5432/onboard"
    db_pool_size: int = 5                    # kept small: free Postgres hosts cap connections
    db_max_overflow: int = 2
    db_pool_recycle_seconds: int = 300       # hosts such as Neon close idle connections; replace them before that bites
    db_connect_timeout_seconds: int = 30     # a sleeping Neon database needs a few seconds to wake up
    max_concurrent_indexing: int = Field(1, ge=1, le=4)   # repositories indexed at the same time (RAM-bound)
    job_timeout_seconds: int = 1800          # a background job running longer than this is marked failed
    cors_origins: list[str] = ["http://localhost:5173"]
    work_dir: str = "/tmp/onboarding_work"
    allow_local_repos: bool = False          # tests / local demos only

    # LLM via LangChain: "<provider>:<model>". Examples: google_genai:gemini-3.6-flash, openai:gpt-5, anthropic:<model>
    llm_model: str = "google_genai:gemini-3.6-flash"   # check availability on your free tier in AI Studio
    llm_api_key: str = Field("", validation_alias=AliasChoices("LLM_API_KEY", "GOOGLE_API_KEY"))
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 4
    llm_min_interval_seconds: float = 4.0    # spacing between calls (LangChain rate limiter) for free-tier limits

    embed_backend: str = "cloudflare"        # cloudflare (Workers AI, free daily allowance) | hash (tests only)
    embed_model: str = "@cf/baai/bge-small-en-v1.5"
    embed_dim: int = 384                     # must match the migrated vector column
    embed_batch_size: int = Field(128, ge=16, le=512)
    # Cloudflare Workers AI credentials and tuning
    cf_account_id: str = Field("", validation_alias=AliasChoices("CF_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID"))
    cf_api_token: str = Field("", validation_alias=AliasChoices("CF_API_TOKEN", "CLOUDFLARE_API_TOKEN"))
    embed_cf_batch_size: int = Field(50, ge=1, le=100)   # texts per request (Cloudflare max is 100)
    embed_cf_concurrency: int = Field(4, ge=1, le=16)    # requests in flight at once
    embed_cf_pooling: str = "cls"                        # keep "cls": the pooling bge-small was trained with

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
    # Git guardrails apply BEFORE analysis; sizes are bytes, not MiB.
    max_clone_bytes: int = Field(200 * 1024 * 1024, ge=1024 * 1024)
    max_checkout_bytes: int = Field(100 * 1024 * 1024, ge=1024 * 1024)
    max_clone_file_bytes: int = Field(20 * 1024 * 1024, ge=1024)
    clone_memory_bytes: int = Field(256 * 1024 * 1024, ge=64 * 1024 * 1024)
    clone_cpu_seconds: int = Field(120, ge=1)
    clone_timeout_seconds: int = Field(300, ge=1)
    clone_min_free_disk_bytes: int = Field(256 * 1024 * 1024, ge=0)

    # --- abuse protection: keeps the free tiers (Gemini, Cloudflare Workers AI, Neon storage) from being drained ---
    # Per-user request limits (in-process, so they apply per server process; see app/core/ratelimit.py).
    rate_limit_enabled: bool = True
    rate_limit_llm_per_minute: int = Field(10, ge=1)      # /ask, /ask/stream and any request that calls the LLM
    rate_limit_llm_per_hour: int = Field(100, ge=1)
    rate_limit_read_per_minute: int = Field(60, ge=1)     # /search, /explain, /impact, /onboarding-tasks
    rate_limit_index_per_hour: int = Field(10, ge=1)      # register, re-index and issue-sync requests
    rate_limit_refresh_per_hour: int = Field(5, ge=1)     # extra /explain?refresh=true request budget
    # Quotas.
    max_repos_per_user: int = Field(5, ge=1)              # repositories one account can keep at the same time
    max_active_jobs_per_user: int = Field(2, ge=1)        # repositories one account can have queued/indexing at once
    max_total_chunks: int = Field(60_000, ge=1)           # all users together; roughly 4-5 KB each in Postgres

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        return normalize_database_url(v)

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret and self.session_secret and self.token_encryption_key)

    # First-week task list (GitHub issues). Optional server token raises GitHub API rate limits.
    github_token: str = ""
    github_api_url: str = "https://api.github.com"
    issue_labels: list[str] = ["good first issue", "good-first-issue", "beginner", "help wanted"]
    issue_max_pages: int = 3
    issue_timeout_seconds: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()
