"""Embeddings through LangChain's `Embeddings` interface (embed_documents / embed_query).

- CloudflareEmbeddings: hosted Cloudflare Workers AI over HTTPS (EMBED_BACKEND=cloudflare, the default). Model
  @cf/baai/bge-small-en-v1.5, 384 dims: nothing to download and almost no RAM on the server.
- HashEmbeddings: deterministic, not semantic; for tests/CI so no network or account is needed.

Any other LangChain embeddings class can replace these: return it from get_embedder() and, if the vector size
differs, set EMBED_DIM + add an Alembic migration + reindex.
"""
import asyncio
import hashlib
import logging
import math
import re
from functools import lru_cache

import httpx
from langchain_core.embeddings import Embeddings

log = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """The embedding provider failed in a way retrying will not fix."""


class EmbeddingQuotaError(EmbeddingError):
    """The provider's free/daily allowance is used up."""


class _BadInput(Exception):
    """HTTP 400-class answer: the text itself was refused (internal signal to split or shorten)."""


class CloudflareEmbeddings(Embeddings):
    """Cloudflare Workers AI text embeddings over the REST API (`@cf/baai/bge-small-en-v1.5` by default).

    - pooling="cls" + L2 normalisation is the pooling bge-small was trained with and normalises like the model's reference code.
      (Cloudflare's own default is mean pooling, which gives less accurate vectors.)
    - bge-small-v1.5 needs no query/passage prefix, so queries and passages are embedded the same way.
    - Requests are sent in batches of `batch_size` (Cloudflare accepts at most 100 texts per call), a few at a time.
    - 429 / 5xx / network errors are retried with backoff. A used-up DAILY allowance raises EmbeddingQuotaError at once,
      because retrying cannot help until 00:00 UTC.
    """
    MAX_BATCH = 100          # Cloudflare's documented per-request maximum for the bge models

    def __init__(self, account_id: str, api_token: str, model: str = "@cf/baai/bge-small-en-v1.5", dim: int = 384,
                 batch_size: int = 50, concurrency: int = 4, pooling: str = "cls", max_retries: int = 5,
                 timeout: float = 60.0, base_url: str = "https://api.cloudflare.com/client/v4",
                 transport: httpx.AsyncBaseTransport | None = None):
        if not account_id or not api_token:
            raise EmbeddingError("EMBED_BACKEND=cloudflare needs CF_ACCOUNT_ID and CF_API_TOKEN.")
        self.url = f"{base_url.rstrip('/')}/accounts/{account_id}/ai/run/{model}"
        self.model, self.dim, self.pooling = model, dim, pooling
        self.batch_size = max(1, min(batch_size, self.MAX_BATCH))
        self.max_retries, self.timeout, self._transport = max_retries, timeout, transport
        self._headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
        self._concurrency = max(1, concurrency)
        self.estimated_tokens = 0       # rough usage counter (chars / 3.5) so you can see how much of the daily pool is used

    # ---- HTTP -------------------------------------------------------------------------------------------------
    async def _post(self, client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
        body = {"text": texts, "pooling": self.pooling}
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.post(self.url, json=body, headers=self._headers)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                if attempt == self.max_retries:
                    raise EmbeddingError(f"Cloudflare embeddings unreachable: {e}") from e
                await asyncio.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            if resp.status_code == 200:
                return self._parse(resp, len(texts))
            detail = self._detail(resp)
            low = detail.lower()
            if resp.status_code in (401, 403):
                raise EmbeddingError(f"Cloudflare rejected the API token ({resp.status_code}): {detail}. "
                                     "Check CF_ACCOUNT_ID and that the token has the 'Workers AI' permission.")
            if "4006" in low or "daily" in low or "free allocation" in low:
                raise EmbeddingQuotaError("Cloudflare Workers AI daily free allowance (10,000 neurons) is used up; "
                                          "it resets at 00:00 UTC. Try again later, or enable the Workers Paid plan.")
            if resp.status_code in (400, 413, 422):
                raise _BadInput(detail)             # caller splits the batch / shortens the text
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == self.max_retries:
                    raise EmbeddingError(f"Cloudflare embeddings failed ({resp.status_code}): {detail}")
                retry_after = resp.headers.get("retry-after", "")
                await asyncio.sleep(min(float(retry_after) if retry_after.isdigit() else delay, 30))
                delay = min(delay * 2, 20)
                continue
            raise EmbeddingError(f"Cloudflare embeddings failed ({resp.status_code}): {detail}")
        raise EmbeddingError("Cloudflare embeddings failed after retries.")      # pragma: no cover

    @staticmethod
    def _detail(resp: httpx.Response) -> str:
        try:
            errs = resp.json().get("errors") or []
            return "; ".join(f"{e.get('code')}: {e.get('message')}" for e in errs) or resp.text[:300]
        except ValueError:
            return resp.text[:300]

    def _parse(self, resp: httpx.Response, expected: int) -> list[list[float]]:
        try:
            data = resp.json()["result"]["data"]
        except (ValueError, KeyError, TypeError) as e:
            raise EmbeddingError(f"Unexpected Cloudflare response: {resp.text[:300]}") from e
        if len(data) != expected or any(len(v) != self.dim for v in data):
            got = len(data[0]) if data else 0
            raise EmbeddingError(f"Cloudflare returned {len(data)} vectors of size {got}; expected {expected} of size "
                                 f"{self.dim}. Check EMBED_MODEL / EMBED_DIM.")
        return [self._unit(v) for v in data]

    @staticmethod
    def _unit(v: list[float]) -> list[float]:
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    async def _embed_batch(self, client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
        """One request; if Cloudflare says the input is invalid (too long, empty), split it, and as a last resort shorten."""
        self.estimated_tokens += int(sum(len(t) for t in texts) / 3.5)
        try:
            return await self._post(client, texts)
        except _BadInput as e:
            if len(texts) > 1:
                mid = len(texts) // 2
                return await self._embed_batch(client, texts[:mid]) + await self._embed_batch(client, texts[mid:])
            short = texts[0][:1000] or " "
            try:
                return await self._post(client, [short])
            except _BadInput:
                raise EmbeddingError(f"Cloudflare rejected a text even after shortening it: {e}") from e

    # ---- LangChain Embeddings interface ---------------------------------------------------------------------------
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        batches = [texts[i:i + self.batch_size] for i in range(0, len(texts), self.batch_size)]
        sem = asyncio.Semaphore(self._concurrency)
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            async def run(b: list[str]) -> list[list[float]]:
                async with sem:
                    return await self._embed_batch(client, b)
            parts = await asyncio.gather(*(run(b) for b in batches))
        return [v for part in parts for v in part]

    async def aembed_query(self, text: str) -> list[float]:
        return (await self.aembed_documents([text]))[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _run_sync(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return _run_sync(self.aembed_query(text))


def _run_sync(coro):
    """Run a coroutine from sync code (never called from inside the running event loop by this app)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")


class HashEmbeddings(Embeddings):
    def __init__(self, dim: int):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            for part in re.split(r"_", tok) + [tok]:
                if part:
                    h = int(hashlib.md5(part.encode()).hexdigest(), 16)
                    v[h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@lru_cache(maxsize=4)
def get_embedder(backend: str, model: str, dim: int, *, cf_account_id: str = "", cf_api_token: str = "",
                 cf_batch_size: int = 50, cf_concurrency: int = 4, cf_pooling: str = "cls") -> Embeddings:
    """Cached: one embedder per process, not one per request."""
    if backend == "hash":
        return HashEmbeddings(dim)
    if backend == "cloudflare":
        return CloudflareEmbeddings(cf_account_id, cf_api_token, model, dim, cf_batch_size, cf_concurrency, cf_pooling)
    raise ValueError(f"Unknown EMBED_BACKEND {backend!r}: use cloudflare or hash.")
