"""Embeddings through LangChain's `Embeddings` interface (embed_documents / embed_query).

Any LangChain embeddings class can replace these (GoogleGenerativeAIEmbeddings, OpenAIEmbeddings, ...): return it
from get_embedder() and, if the vector size differs, set EMBED_DIM + add an Alembic migration + reindex.

- FastEmbedEmbeddings: free local ONNX models via fastembed (no torch). Default BAAI/bge-small-en-v1.5 (384 dims).
  For code-specific vectors use EMBED_MODEL=jinaai/jina-embeddings-v2-base-code and EMBED_DIM=768.
- HashEmbeddings: deterministic, not semantic; for tests/CI so no model download is needed.
"""
import hashlib
import math
import re
from functools import lru_cache

from langchain_core.embeddings import Embeddings


class FastEmbedEmbeddings(Embeddings):
    def __init__(self, model_name: str, dim: int, batch_size: int = 128, parallelism: int = 2,
                 parallel_min_chunks: int = 2000):
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model_name=model_name)   # downloads once, then cached on disk
        self.dim = dim
        self.batch_size = batch_size
        self.parallelism = parallelism
        self.parallel_min_chunks = parallel_min_chunks

    def iter_embed_documents(self, texts: list[str]):
        """Yield vectors from one persistent FastEmbed data-parallel job."""
        # A worker pool costs seconds to start and one model copy per process: only worth it for big corpora.
        use_pool = self.parallelism > 1 and len(texts) >= self.parallel_min_chunks
        parallel = self.parallelism if use_pool else None
        for vector in self._model.passage_embed(texts, batch_size=self.batch_size, parallel=parallel):
            yield vector.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return list(self.iter_embed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed([text]))).tolist()   # bge models embed queries differently


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
def get_embedder(backend: str, model: str, dim: int, batch_size: int = 128, parallelism: int = 2,
                 parallel_min_chunks: int = 2000) -> Embeddings:
    """Cached: the model is loaded once per process, not once per request."""
    if backend == "hash":
        return HashEmbeddings(dim)
    return FastEmbedEmbeddings(model, dim, batch_size, parallelism, parallel_min_chunks)
