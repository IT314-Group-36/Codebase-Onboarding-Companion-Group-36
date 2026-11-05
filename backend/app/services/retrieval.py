"""Hybrid retrieval over pgvector + Postgres full-text, fused with Reciprocal Rank Fusion."""
import re
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForRetrieverRun, CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models import Chunk

_STOP = {"the", "and", "for", "are", "how", "what", "where", "which", "does", "that", "this", "with", "from",
         "into", "about", "when", "who", "why", "can", "was", "were", "has", "have", "not", "you", "your", "its",
         "there", "their", "they", "them", "than", "then", "will", "would", "should", "could", "is", "it", "of",
         "in", "on", "to", "a", "an", "do", "i", "we"}


def fts_query(text: str) -> str | None:
    """OR-query from the question's meaningful words (plainto_tsquery would AND them and match nothing)."""
    words = [w for w in re.findall(r"[A-Za-z0-9_]+", text.lower()) if len(w) >= 3 and w not in _STOP]
    return " | ".join(dict.fromkeys(words)) or None


async def hybrid_search(session: AsyncSession, repo_id: int, query: str, embedder, k: int = 8, pool: int = 30) -> list[dict]:
    qvec = await embedder.aembed_query(query)
    vec_ids = (await session.execute(
        select(Chunk.id).where(Chunk.repo_id == repo_id)
        .order_by(Chunk.embedding.cosine_distance(qvec)).limit(pool))).scalars().all()
    score: dict[int, float] = {}
    for rank, cid in enumerate(vec_ids, 1):
        score[cid] = score.get(cid, 0.0) + 1.0 / (60 + rank)
    q = fts_query(query)
    if q:
        tsq = func.to_tsquery("simple", q)
        fts_ids = (await session.execute(
            select(Chunk.id).where(Chunk.repo_id == repo_id, Chunk.content_tsv.op("@@")(tsq))
            .order_by(func.ts_rank_cd(Chunk.content_tsv, tsq).desc()).limit(pool))).scalars().all()
        for rank, cid in enumerate(fts_ids, 1):
            score[cid] = score.get(cid, 0.0) + 1.0 / (60 + rank)
    top = sorted(score, key=score.get, reverse=True)[:k]
    if not top:
        return []
    rows = (await session.execute(
        select(Chunk.id, Chunk.file_path, Chunk.symbol_uid, Chunk.start_line, Chunk.end_line, Chunk.content)
        .where(Chunk.id.in_(top)))).all()
    by_id = {r.id: r for r in rows}
    return [{"file_path": by_id[i].file_path, "symbol_uid": by_id[i].symbol_uid, "start_line": by_id[i].start_line,
             "end_line": by_id[i].end_line, "content": by_id[i].content, "score": round(score[i], 5)}
            for i in top if i in by_id]


class PgHybridRetriever(BaseRetriever):
    """LangChain retriever over OUR pgvector + full-text SQL (hybrid_search above is unchanged).

    Use it like any retriever: `docs = await PgHybridRetriever(repo_id=1, embeddings=emb, k=8).ainvoke(question)`.
    Document.metadata: file_path, symbol_uid, start_line, end_line, score.
    """
    repo_id: int
    embeddings: Any
    k: int = 8

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        raise NotImplementedError("Database access is async: use `await retriever.ainvoke(query)`.")

    async def _aget_relevant_documents(self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun) -> list[Document]:
        async with SessionLocal() as session:
            hits = await hybrid_search(session, self.repo_id, query, self.embeddings, k=self.k)
        return [Document(page_content=h["content"],
                         metadata={k: h[k] for k in ("file_path", "symbol_uid", "start_line", "end_line", "score")})
                for h in hits]


def doc_to_hit(doc: Document) -> dict:
    """Document -> the JSON shape the API has always returned."""
    return {**{k: doc.metadata[k] for k in ("file_path", "symbol_uid", "start_line", "end_line")},
            "content": doc.page_content, "score": doc.metadata["score"]}
