"""Process-wide singletons: chat model and embeddings are built once, not per request."""
from functools import lru_cache

from ai_pipeline.embeddings import get_embedder as _get_embedder
from ai_pipeline.llm import build_chat_model
from app.core.config import get_settings


@lru_cache
def get_llm():
    """A LangChain chat model, or None when no API key is set (the app degrades gracefully)."""
    s = get_settings()
    if not s.llm_api_key:
        return None
    return build_chat_model(s.llm_model, s.llm_api_key, s.llm_timeout_seconds, s.llm_max_retries,
                            s.llm_min_interval_seconds)


def get_embedder():
    """A LangChain Embeddings object."""
    s = get_settings()
    return _get_embedder(s.embed_backend, s.embed_model, s.embed_dim)
