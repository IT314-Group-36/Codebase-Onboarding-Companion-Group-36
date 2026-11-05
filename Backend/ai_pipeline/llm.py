"""LLM access through LangChain.

`build_chat_model("<provider>:<model>", ...)` returns any LangChain chat model, so switching provider/model is a
setting (LLM_MODEL=openai:gpt-5, anthropic:..., google_genai:...), plus the provider's langchain-* package.
Free-tier protection uses LangChain's own rate limiter + timeout + retries (no custom throttle code).
"""
from langchain.chat_models import init_chat_model
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable
from pydantic import ValidationError


def build_chat_model(model: str, api_key: str, timeout_s: int = 60, max_retries: int = 4,
                     min_interval_s: float = 4.0) -> BaseChatModel:
    """model format: '<provider>:<model name>', e.g. 'google_genai:gemini-3.6-flash'.

    Sampling parameters (temperature, ...) are left unset on purpose: the Gemini wrapper omits them for Gemini 3+,
    where Google deprecates them.
    """
    limiter = (InMemoryRateLimiter(requests_per_second=1.0 / min_interval_s, check_every_n_seconds=0.1,
                                   max_bucket_size=1) if min_interval_s > 0 else None)
    return init_chat_model(model, api_key=api_key, timeout=timeout_s, max_retries=max_retries, rate_limiter=limiter)


def structured_chain(prompt, llm: BaseChatModel, schema: type) -> Runnable:
    """prompt | model-with-structured-output, retried once if the model returns malformed output."""
    chain = prompt | llm.with_structured_output(schema)
    return chain.with_retry(retry_if_exception_type=(OutputParserException, ValidationError), stop_after_attempt=2)
