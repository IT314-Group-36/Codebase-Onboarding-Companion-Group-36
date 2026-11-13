"""Indexing job: clone -> analyze -> embed -> save (one atomic swap) -> describe (LLM, with fallback).

Blocking work (git, tree-sitter, embeddings) runs in threads; DB and LLM calls are async."""
import asyncio
import logging
import uuid
from itertools import islice
from pathlib import Path

from sqlalchemy import delete, insert, update

from ai_pipeline.chunker import embed_text
from ai_pipeline.module_map import deterministic_module_map, generate_module_map
from ai_pipeline.parser import language_of
from ai_pipeline.pipeline import analyze_checkout
from ai_pipeline.repo import clone_repo, safe_rmtree, validate_branch, validate_repo_url
from ai_pipeline.stack_detector import EXT_LANG
from ai_pipeline.summary import RETRIEVAL_QUERIES, format_context, generate_summary
from app.core.config import get_settings
from app.core.security import SecurityConfigError, TokenDecryptError, decrypt_token
from app.db.session import SessionLocal
from app.models import Chunk, Edge, Explanation, File, Repository, Symbol, User
from app.services.retrieval import PgHybridRetriever

log = logging.getLogger(__name__)


def _take(iterator, count: int) -> list:
    """Pull a bounded slice from a blocking embedding iterator without leaking StopIteration."""
    return list(islice(iterator, count))


async def _update(repo_id: int, **fields) -> None:
    async with SessionLocal() as s:
        await s.execute(update(Repository).where(Repository.id == repo_id).values(**fields))
        await s.commit()


async def _bulk(session, model, rows: list[dict], size: int = 500) -> None:
    for i in range(0, len(rows), size):
        await session.execute(insert(model), rows[i:i + size])


async def _save(repo_id: int, sha: str, a, vectors: list[list[float]]) -> None:
    """Replace the repo's data atomically: readers keep seeing the old index until this commits."""
    from pathlib import PurePosixPath
    async with SessionLocal() as s, s.begin():
        for m in (Chunk, Edge, Symbol, File, Explanation):      # cached explanations describe the old code
            await s.execute(delete(m).where(m.repo_id == repo_id))
        safe = set(a.safe_files)
        await _bulk(s, File, [{"repo_id": repo_id, "path": p, "size": a.file_sizes.get(p, 0), "sensitive": p not in safe,
                               "language": EXT_LANG.get(PurePosixPath(p).suffix.lower()) or language_of(p)}
                              for p in a.all_files])
        await _bulk(s, Symbol, [{"repo_id": repo_id, "uid": sym.uid, "file_path": sym.path, "name": sym.name,
                                 "qualname": sym.qualname, "kind": sym.kind, "start_line": sym.start_line,
                                 "end_line": sym.end_line, "signature": sym.signature}
                                for pf in a.parsed.values() for sym in pf.symbols])
        edges = [{"repo_id": repo_id, "kind": "imports", "src": x, "dst": y} for x, y in a.file_graph.edges]
        edges += [{"repo_id": repo_id, "kind": "calls", "src": x, "dst": y} for x, y in a.symbol_graph.edges]
        await _bulk(s, Edge, edges)
        await _bulk(s, Chunk, [{"repo_id": repo_id, "file_path": c.metadata["file_path"], "symbol_uid": c.metadata["symbol_uid"],
                                "start_line": c.metadata["start_line"], "end_line": c.metadata["end_line"],
                                "content": c.page_content, "embedding": v}
                               for c, v in zip(a.chunks, vectors, strict=True)], size=1000)
        await s.execute(update(Repository).where(Repository.id == repo_id).values(
            commit_sha=sha, tech_stack=a.tech_stack, index_report=a.report, stage="describing"))


async def _describe(repo_id: int, root: Path, a, llm, embedder) -> tuple[dict, dict | None, list[str]]:
    warnings: list[str] = []
    module_map = summary = None
    if llm is None:
        warnings.append("No LLM API key is set (LLM_API_KEY): used the deterministic module map and skipped the summary.")
    else:
        try:
            module_map, w = await generate_module_map(llm, root, a.all_files, a.tech_stack, a.file_graph)
            warnings += w
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Module-map LLM step failed ({e}); used the deterministic module map.")
        try:
            retriever = PgHybridRetriever(repo_id=repo_id, embeddings=embedder, k=3)
            docs = [d for q in RETRIEVAL_QUERIES for d in await retriever.ainvoke(q)]
            summary, w = await generate_summary(llm, root, a.all_files, a.tech_stack, format_context(docs))
            warnings += w
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Summary LLM step failed ({e}).")
    if module_map is None:
        module_map = deterministic_module_map(a.all_files, a.file_graph, a.tech_stack)
    return module_map.model_dump(), (summary.model_dump() if summary else None), warnings


async def _saved_token(repo_id: int) -> str | None:
    """The repo owner's GitHub token (stored encrypted at sign-in), or None if there is none."""
    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        user = await s.get(User, repo.owner_id) if repo is not None and repo.owner_id is not None else None
        cipher = user.encrypted_access_token if user is not None else None
    if not cipher:
        return None
    try:
        return decrypt_token(cipher)
    except (TokenDecryptError, SecurityConfigError) as e:
        raise RuntimeError("Could not clone the repo: your saved GitHub sign-in can no longer be used. "
                           "Sign in with GitHub again, then retry.") from e


def _explain_failure_with_token(err: str) -> str:
    low = err.lower()
    if "authentication failed" in low or "invalid username" in low or "bad credentials" in low:
        head = "Could not clone the repo: GitHub rejected your saved sign-in. Sign in with GitHub again, then retry."
    else:
        head = ("Could not clone the repo with your GitHub account. If it is private, check the URL and that your account "
                "can access it (for an organization's repo, an owner may need to approve this app on GitHub).")
    return head + "\n" + err.partition("\n")[2]


async def _clone(repo_id: int, url: str, branch: str, dest: Path, pasted_token: str | None) -> str:
    """Clone with the pasted token if given. Otherwise try anonymously first (public repos, and a revoked saved token
    can never break them), and only if that fails use the owner's saved GitHub token (private repos)."""
    if pasted_token:
        return await asyncio.to_thread(clone_repo, url, branch, dest, pasted_token)
    try:
        return await asyncio.to_thread(clone_repo, url, branch, dest, None)
    except RuntimeError as anonymous_error:
        low = str(anonymous_error).lower()
        if "remote branch" in low or "timed out" in low:      # the repo is reachable; a token would not help
            raise
        saved = await _saved_token(repo_id)
        if not saved:
            raise
    try:
        return await asyncio.to_thread(clone_repo, url, branch, dest, saved)
    except RuntimeError as e:
        raise RuntimeError(_explain_failure_with_token(str(e))) from e


async def run_indexing(repo_id: int, access_token: str | None, *, llm, embedder) -> None:
    cfg = get_settings()
    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        if repo is None:
            return
        url, branch = repo.url, repo.branch
    work = Path(cfg.work_dir) / f"job_{repo_id}_{uuid.uuid4().hex[:8]}"     # one directory per job
    try:
        await _update(repo_id, status="indexing", stage="cloning", error=None)
        url = validate_repo_url(url, cfg.allow_local_repos)                   # defence in depth (also checked by the API)
        branch = validate_branch(branch)
        sha = await _clone(repo_id, url, branch, work / "clone", access_token)
        await _update(repo_id, stage="analyzing")
        a = await asyncio.to_thread(analyze_checkout, work / "clone", max_chunks=cfg.max_chunks,
                                    max_file_bytes=cfg.max_file_bytes)
        await _update(repo_id, stage="embedding")
        texts = [embed_text(c) for c in a.chunks]
        total = len(texts)
        vectors = []
        batch_size = max(1, cfg.embed_batch_size)
        if hasattr(embedder, "iter_embed_documents"):
            # FastEmbed owns a persistent worker pool for this full corpus; consume it in
            # bounded slices so the UI gets progress without restarting workers per batch.
            iterator = iter(embedder.iter_embed_documents(texts))
            try:
                while True:
                    batch_vectors = await asyncio.to_thread(_take, iterator, batch_size)
                    if not batch_vectors:
                        break
                    vectors.extend(batch_vectors)
                    await _update(repo_id, index_report={
                        **a.report,
                        "embedding_progress": {"completed": len(vectors), "total": total},
                    })
            finally:
                close = getattr(iterator, "close", None)      # stops FastEmbed's worker pool if we bail out early
                if close:
                    await asyncio.to_thread(close)
        else:
            for start in range(0, total, batch_size):
                end = min(start + batch_size, total)
                vectors.extend(await embedder.aembed_documents(texts[start:end]))
                await _update(repo_id, index_report={
                    **a.report,
                    "embedding_progress": {"completed": end, "total": total},
                })
        await _update(repo_id, stage="saving")
        await _save(repo_id, sha, a, vectors)
        module_map, summary, warnings = await _describe(repo_id, work / "clone", a, llm, embedder)
        await _update(repo_id, status="ready", stage=None, module_map=module_map, summary=summary, warnings=warnings)
    except Exception as e:  # noqa: BLE001
        log.exception("indexing repo %s failed", repo_id)
        await _update(repo_id, status="failed", stage=None, error=str(e)[:1000])
    finally:
        await asyncio.to_thread(safe_rmtree, work)                            # DR-03: never keep the clone
