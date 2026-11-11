"""The LangChain wiring itself (no network, no database): chat-model config, structured-output binding,
prompt rendering, parse-retry behaviour, the Embeddings interface and settings compatibility."""
import warnings

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import RunnableLambda

from ai_pipeline import module_map, summary
from ai_pipeline.embeddings import HashEmbeddings, get_embedder
from ai_pipeline.llm import build_chat_model, structured_chain
from ai_pipeline.module_map import ModuleMap
from ai_pipeline.summary import RepoSummary
from app.core.config import Settings
from app.services.qa import (FILE_EXPLAIN_PROMPT, IMPACT_PROMPT, NL_IMPACT_PROMPT, QA_PROMPT, SYMBOL_EXPLAIN_PROMPT, Answer,
                             FileExplanation, ImpactExplanation, SymbolExplanation)

warnings.filterwarnings("ignore")


def test_chat_model_is_built_from_a_provider_model_string():
    m = build_chat_model("google_genai:gemini-3.6-flash", "dummy-key", timeout_s=42, max_retries=3, min_interval_s=4.0)
    assert type(m).__name__ == "ChatGoogleGenerativeAI" and m.model == "gemini-3.6-flash"
    assert m.timeout == 42 and m.max_retries == 3 and m.rate_limiter is not None
    assert m.rate_limiter.requests_per_second == pytest.approx(0.25)       # one call every 4s: free-tier friendly
    assert build_chat_model("google_genai:gemini-3.6-flash", "k", min_interval_s=0).rate_limiter is None


@pytest.mark.parametrize("schema", [ModuleMap, RepoSummary, Answer, ImpactExplanation, FileExplanation, SymbolExplanation])
def test_every_schema_binds_to_the_real_chat_model(schema):
    m = build_chat_model("google_genai:gemini-3.6-flash", "dummy-key")
    assert m.with_structured_output(schema) is not None                    # schema conversion happens at bind time


def test_prompts_render_even_when_values_contain_braces():
    tricky = 'json {"a": 1} and {placeholder} and ``` fences'
    cases = [
        (module_map._PROMPT, dict(tech_stack=tricky, readme=tricky, tree=tricky, facts=tricky)),
        (summary._PROMPT, dict(tech_stack=tricky, readme=tricky, tree=tricky, context=tricky)),
        (QA_PROMPT, dict(question=tricky, excerpts=tricky)),
        (IMPACT_PROMPT, dict(target=tricky, callers=tricky, files=tricky)),
        (NL_IMPACT_PROMPT, dict(question=tricky, target=tricky, facts=tricky)),
        (FILE_EXPLAIN_PROMPT, dict(project=tricky, module=tricky, path=tricky, relationships=tricky, symbols=tricky, code=tricky)),
        (SYMBOL_EXPLAIN_PROMPT, dict(project=tricky, module=tricky, target=tricky, kind=tricky, path=tricky, signature=tricky,
                                     relationships=tricky, code=tricky)),
    ]
    for prompt, variables in cases:
        assert set(prompt.input_variables) == set(variables)
        msgs = prompt.format_messages(**variables)
        assert [m.type for m in msgs] == ["system", "human"] and tricky in msgs[1].content
        assert "untrusted DATA" in msgs[0].content                          # prompt-injection guard is in every prompt


class _Flaky:
    """A chat model whose structured output fails `n` times with a parse error before succeeding."""

    def __init__(self, n):
        self.n, self.attempts = n, 0

    def with_structured_output(self, schema, **kw):
        def run(_):
            self.attempts += 1
            if self.attempts <= self.n:
                raise OutputParserException("malformed")
            return ImpactExplanation(explanation="ok", suggested_checks=[])
        return RunnableLambda(run)


async def test_structured_chain_retries_once_on_malformed_output():
    ok = _Flaky(1)
    out = await structured_chain(IMPACT_PROMPT, ok, ImpactExplanation).ainvoke({"target": "t", "callers": "c", "files": "f"})
    assert out.explanation == "ok" and ok.attempts == 2
    bad = _Flaky(5)
    with pytest.raises(OutputParserException):
        await structured_chain(IMPACT_PROMPT, bad, ImpactExplanation).ainvoke({"target": "t", "callers": "c", "files": "f"})
    assert bad.attempts == 2                                                # gives up after two tries, not forever


async def test_embeddings_follow_the_langchain_interface():
    e = get_embedder("hash", "x", 384)
    assert isinstance(e, Embeddings) and isinstance(e, HashEmbeddings) and e.dim == 384
    assert e is get_embedder("hash", "x", 384)                              # cached singleton
    docs = ["def charge_card(): pass", "class Shop: ..."]
    assert await e.aembed_documents(docs) == e.embed_documents(docs)
    q = await e.aembed_query("where is payment logic")
    assert len(q) == 384 and q == e.embed_query("where is payment logic")


def test_existing_env_files_keep_working(monkeypatch):
    """Old .env files used GOOGLE_API_KEY; the new name is LLM_API_KEY. Both must populate the same setting."""
    for var in ("LLM_API_KEY", "GOOGLE_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "old-name-key")
    assert Settings(_env_file=None).llm_api_key == "old-name-key"
    monkeypatch.setenv("LLM_API_KEY", "new-name-key")
    assert Settings(_env_file=None).llm_api_key == "new-name-key"
    assert Settings(_env_file=None).llm_model == "google_genai:gemini-3.6-flash"
