"""CloudflareEmbeddings against a fake Workers AI (httpx.MockTransport): no network, no account needed."""
import json
import math

import httpx
import pytest

from ai_pipeline.embeddings import (
    CloudflareEmbeddings,
    EmbeddingError,
    EmbeddingQuotaError,
    HashEmbeddings,
    get_embedder,
)

DIM = 4


def _ok(texts):
    return httpx.Response(200, json={"success": True, "errors": [], "result": {
        "shape": [len(texts), DIM], "data": [[float(len(t) or 1), 1.0, 0.0, 0.0] for t in texts]}})


def _emb(handler, **kw):
    return CloudflareEmbeddings("acc", "tok", dim=DIM, transport=httpx.MockTransport(handler), max_retries=2, **kw)


async def test_batches_are_split_ordered_and_normalised():
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        assert req.headers["authorization"] == "Bearer tok"
        assert req.url.path.endswith("/accounts/acc/ai/run/@cf/baai/bge-small-en-v1.5")
        assert body["pooling"] == "cls"                     # must match the local bge model
        assert len(body["text"]) <= 3
        return _ok(body["text"])

    e = _emb(handler, batch_size=3, concurrency=2)
    texts = ["a" * n for n in range(1, 11)]
    vecs = await e.aembed_documents(texts)
    assert len(vecs) == 10 and len(seen) == 4
    for n, v in zip(range(1, 11), vecs):
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0)
        assert v[0] > 0 and math.isclose(v[0] / v[1], float(n))     # order kept: vector i belongs to text i


async def test_query_and_sync_wrappers():
    e = _emb(lambda r: _ok(json.loads(r.content)["text"]))
    assert len(await e.aembed_query("x")) == DIM
    assert len(e.embed_query("x")) == DIM                          # sync path (used outside the event loop)
    assert len(e.embed_documents(["a", "b"])) == 2


async def test_retries_rate_limit_then_succeeds(monkeypatch):
    async def no_sleep(_):
        return None
    monkeypatch.setattr("ai_pipeline.embeddings.asyncio.sleep", no_sleep)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"errors": [{"code": 3040, "message": "Too many requests"}]})
        return _ok(json.loads(req.content)["text"])

    assert len(await _emb(handler).aembed_documents(["a"])) == 1 and calls["n"] == 3


async def test_daily_quota_fails_fast_without_retrying():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, json={"errors": [{"code": 4006, "message":
            "you have used up your daily free allocation of 10,000 neurons"}]})

    with pytest.raises(EmbeddingQuotaError, match="00:00 UTC"):
        await _emb(handler).aembed_documents(["a"])
    assert calls["n"] == 1


async def test_bad_token_gives_a_helpful_error():
    h = lambda r: httpx.Response(403, json={"errors": [{"code": 10000, "message": "Authentication error"}]})  # noqa: E731
    with pytest.raises(EmbeddingError, match="Workers AI"):
        await _emb(h).aembed_documents(["a"])


async def test_rejected_input_is_split_then_shortened():
    sizes = []

    def handler(req):
        texts = json.loads(req.content)["text"]
        sizes.append([len(t) for t in texts])
        if len(texts) > 1 or len(texts[0]) > 1000:
            return httpx.Response(400, json={"errors": [{"code": 5006, "message": "input too long"}]})
        return _ok(texts)

    vecs = await _emb(handler, batch_size=4).aembed_documents(["a", "b", "c" * 5000, "d"])
    assert len(vecs) == 4
    assert [1000] in sizes                                         # the long text was cut to 1000 chars as a last resort


async def test_wrong_dimension_is_reported():
    h = lambda r: httpx.Response(200, json={"result": {"data": [[0.1, 0.2]]}})  # noqa: E731
    with pytest.raises(EmbeddingError, match="EMBED_DIM"):
        await _emb(h).aembed_documents(["a"])


def test_missing_credentials_and_factory():
    with pytest.raises(EmbeddingError, match="CF_ACCOUNT_ID"):
        CloudflareEmbeddings("", "")
    assert isinstance(get_embedder("hash", "m", 8), HashEmbeddings)
    assert isinstance(get_embedder("cloudflare", "@cf/baai/bge-small-en-v1.5", 384, cf_account_id="a", cf_api_token="t"),
                      CloudflareEmbeddings)
    with pytest.raises(ValueError, match="Unknown EMBED_BACKEND"):
        get_embedder("nope", "m", 8)
