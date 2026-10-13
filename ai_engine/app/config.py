from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Optional: real LLM (Google Gemini, free tier via https://aistudio.google.com/apikey).
    # Without a key the engine answers with offline heuristics.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"  # free-tier model; alternative: gemini-3.1-flash-lite
    llm_timeout: int = 30
    # Optional shared secret: backend sends it as "Authorization: Bearer <key>"
    engine_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
