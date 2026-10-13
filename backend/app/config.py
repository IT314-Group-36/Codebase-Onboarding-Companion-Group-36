from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Codebase Onboarding Companion API"
    # SQLite works out of the box; set a postgresql+psycopg2:// URL for Postgres.
    database_url: str = "sqlite:///./onboarding.db"
    repos_dir: str = "./data/repos"
    allow_local_paths: bool = True
    clone_timeout: int = 300
    max_file_bytes: int = 500_000

    # AI API team's engine. If unset, heuristic fallbacks are used.
    ai_api_url: str | None = None
    ai_api_key: str | None = None
    ai_timeout: int = 25

    github_token: str | None = None
    cors_origins: str = "*"  # comma-separated

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
