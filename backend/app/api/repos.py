from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline.graph import impact as run_impact
from ai_pipeline.graph import module_graph
from ai_pipeline.repo import validate_branch, validate_repo_url
from app.api.deps import (
    get_current_user,
    get_embedder_dep,
    get_llm_dep,
    get_queue,
    get_ready_user_repo,
    get_user_repo,
)
from app.core.config import get_settings
from app.db.session import get_session
from app.models import Edge, File, Repository, Symbol, User
from app.schemas import AskIn, FileOut, ReindexIn, RepoCreate, RepoDetail, RepoOut, SearchIn, SymbolOut
from app.services.graph_service import find_symbols, load_graphs
from app.services.qa import LLMCallError, answer_question, explain_impact
from app.services.retrieval import PgHybridRetriever, doc_to_hit

router = APIRouter(prefix="/repos", tags=["repos"])
CAVEAT = "Static analysis: dynamic calls, reflection and string-based imports are not visible. Treat as 'likely affected'."


@router.post("", response_model=RepoOut, status_code=202)
async def register_repo(body: RepoCreate, user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session), queue=Depends(get_queue)):
    try:
        url = validate_repo_url(body.url, get_settings().allow_local_repos)
        branch = validate_branch(body.branch)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    existing = (await session.execute(select(Repository).where(
        Repository.owner_id == user.id, Repository.url == url, Repository.branch == branch))).scalar_one_or_none()
    if existing:                                  # idempotent: use POST /repos/{id}/reindex to refresh
        return existing
    repo = Repository(owner_id=user.id, url=url, branch=branch, status="queued")
    session.add(repo)
    await session.commit()
    # No pasted token: the worker loads the owner's saved GitHub token itself if the repo turns out to be private,
    # so the token never travels through the job queue.
    await queue.enqueue_job("index_repository", repo.id, body.access_token)
    return repo


@router.get("", response_model=list[RepoOut])
async def list_repos(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return (await session.execute(
        select(Repository).where(Repository.owner_id == user.id).order_by(Repository.id.desc()))).scalars().all()


@router.get("/{repo_id}", response_model=RepoDetail)
async def repo_detail(repo: Repository = Depends(get_user_repo)):
    return repo


@router.post("/{repo_id}/reindex", response_model=RepoOut, status_code=202)
async def reindex(body: ReindexIn | None = None, repo: Repository = Depends(get_user_repo),
                  session: AsyncSession = Depends(get_session), queue=Depends(get_queue)):
    if repo.status in ("queued", "indexing"):
        raise HTTPException(409, "Indexing is already in progress")
    repo.status, repo.stage, repo.error = "queued", None, None
    await session.commit()
    await session.refresh(repo)       # server-side updated_at is expired after UPDATE; async can't lazy-load it
    await queue.enqueue_job("index_repository", repo.id, body.access_token if body else None)
    return repo


@router.get("/{repo_id}/files", response_model=list[FileOut])
async def list_files(repo: Repository = Depends(get_ready_user_repo), session: AsyncSession = Depends(get_session)):
    return (await session.execute(select(File).where(File.repo_id == repo.id).order_by(File.path))).scalars().all()


@router.get("/{repo_id}/files/{path:path}")
async def file_detail(path: str, repo: Repository = Depends(get_ready_user_repo), session: AsyncSession = Depends(get_session)):
    f = (await session.execute(select(File).where(File.repo_id == repo.id, File.path == path))).scalar_one_or_none()
    if f is None:
        raise HTTPException(404, "File not found")
    syms = (await session.execute(select(Symbol).where(Symbol.repo_id == repo.id, Symbol.file_path == path)
                                  .order_by(Symbol.start_line))).scalars().all()
    imports = (await session.execute(select(Edge.dst).where(Edge.repo_id == repo.id, Edge.kind == "imports", Edge.src == path))).scalars().all()
    imported_by = (await session.execute(select(Edge.src).where(Edge.repo_id == repo.id, Edge.kind == "imports", Edge.dst == path))).scalars().all()
    return {"file": FileOut.model_validate(f, from_attributes=True), "symbols": [SymbolOut.model_validate(s, from_attributes=True) for s in syms],
            "imports": sorted(imports), "imported_by": sorted(imported_by)}


@router.get("/{repo_id}/map")
async def get_map(repo: Repository = Depends(get_ready_user_repo), session: AsyncSession = Depends(get_session)):
    """Module map (LLM or deterministic) + module-to-module dependency graph for the visual map."""
    raw_edges = (await session.execute(
        select(Edge.src, Edge.dst, Edge.kind).where(
            Edge.repo_id == repo.id,
            Edge.kind.in_(("imports", "calls")),
        )
    )).all()
    file_edges: list[tuple[str, str]] = []
    for src, dst, kind in raw_edges:
        if kind == "calls":
            src_file = src.split("::", 1)[0]
            dst_file = dst.split("::", 1)[0]
        else:
            src_file, dst_file = src, dst
        file_edges.append((src_file, dst_file))
    mm = repo.module_map or {"modules": [], "entry_points": [], "project_summary": ""}
    return {"project_summary": mm.get("project_summary"), "modules": mm["modules"], "entry_points": mm["entry_points"],
            "graph": module_graph(mm["modules"], file_edges), "tech_stack": repo.tech_stack}


@router.get("/{repo_id}/symbols", response_model=list[SymbolOut])
async def search_symbols(q: str = Query(min_length=1), limit: int = Query(20, le=100),
                         repo: Repository = Depends(get_ready_user_repo), session: AsyncSession = Depends(get_session)):
    return await find_symbols(session, repo.id, q, limit)


@router.post("/{repo_id}/search")
async def search_code(body: SearchIn, repo: Repository = Depends(get_ready_user_repo), embedder=Depends(get_embedder_dep)):
    """Retrieval only (no LLM): hybrid vector + keyword search over code chunks."""
    docs = await PgHybridRetriever(repo_id=repo.id, embeddings=embedder, k=body.k).ainvoke(body.query)
    return {"hits": [doc_to_hit(d) for d in docs]}


@router.post("/{repo_id}/ask")
async def ask(body: AskIn, repo: Repository = Depends(get_ready_user_repo), embedder=Depends(get_embedder_dep),
              llm=Depends(get_llm_dep)):
    if llm is None:
        raise HTTPException(503, "LLM is not configured (set LLM_API_KEY). /search works without it.")
    try:
        return await answer_question(llm, embedder, repo.id, body.question)
    except LLMCallError as e:
        raise HTTPException(502, f"The LLM call failed: {str(e)[:300]}") from e


@router.get("/{repo_id}/impact")
async def impact(symbol: str | None = None, file: str | None = None, depth: int = Query(3, ge=1, le=6),
                 explain: bool = False, repo: Repository = Depends(get_ready_user_repo),
                 session: AsyncSession = Depends(get_session), llm=Depends(get_llm_dep)):
    """What is likely affected if this symbol (uid or name) or file changes? Reverse traversal with NetworkX."""
    if not symbol and not file:
        raise HTTPException(422, "Provide ?symbol=<uid or name> or ?file=<path>")
    fg, sg = await load_graphs(session, repo.id)
    if file:
        if file not in fg:
            raise HTTPException(404, "File not found")
        uids, files, target = [n for n, d in sg.nodes(data=True) if d["path"] == file], [file], file
    else:
        matches = await find_symbols(session, repo.id, symbol, limit=10)
        exact = [m for m in matches if m.uid == symbol] or ([matches[0]] if len(matches) == 1 else [m for m in matches if m.name == symbol])
        if len(exact) != 1:
            if not matches:
                raise HTTPException(404, "No symbol matches")
            raise HTTPException(409, {"message": "Ambiguous symbol; pass an exact uid",
                                      "candidates": [{"uid": m.uid, "file_path": m.file_path, "kind": m.kind} for m in matches]})
        uids, files, target = [exact[0].uid], [], exact[0].uid
    result = run_impact(sg, fg, uids, files, depth)
    out = {"target": target, "depth": depth, **result, "caveat": CAVEAT, "explanation": None}
    if explain:
        if llm is None:
            raise HTTPException(503, "LLM is not configured (set LLM_API_KEY)")
        try:
            out["explanation"] = await explain_impact(llm, target, result)
        except LLMCallError as e:
            raise HTTPException(502, f"The LLM call failed: {str(e)[:300]}") from e
    return out
