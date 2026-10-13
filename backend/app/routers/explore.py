from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FileRecord, ImportEdge, Repository, Symbol
from ..schemas import (FileExplanation, FileSummary, Graph, GraphEdge, GraphNode, ModuleOut, RepoMap,
                       RepoOut, SourceOut, SymbolOut)
from ..services.ai_client import ai_client
from ..services.analyzer import NON_CODE, describe_module
from ..services.ingest import read_repo_file
from fastapi import HTTPException
from .deps import get_ready_repo

router = APIRouter(prefix="/api/v1/repos/{repo_id}", tags=["Explore"])


@router.get("/map", response_model=RepoMap, summary="Module map with responsibilities")
def repo_map(repo: Repository = Depends(get_ready_repo), db: Session = Depends(get_db)):
    files = db.scalars(select(FileRecord).where(FileRecord.repo_id == repo.id)).all()
    by_module: dict[str, list[FileRecord]] = defaultdict(list)
    for f in files:
        by_module[f.module].append(f)
    modules = []
    for name, fs in by_module.items():
        langs = [l for l, _ in Counter(f.language for f in fs if f.language not in NON_CODE).most_common(3)]
        key = sorted(fs, key=lambda f: f.line_count, reverse=True)[:5]
        modules.append(ModuleOut(name=name, description=describe_module(name, fs, langs), file_count=len(fs),
                                 line_count=sum(f.line_count for f in fs), languages=langs,
                                 key_files=[FileSummary.model_validate(f) for f in key]))
    modules.sort(key=lambda m: m.line_count, reverse=True)
    return RepoMap(repo=RepoOut.model_validate(repo), modules=modules)


@router.get("/files", response_model=list[FileSummary], summary="List/filter files")
def list_files(module: str | None = None, language: str | None = None, q: str | None = Query(None, description="path contains"),
               limit: int = Query(100, le=500), offset: int = 0,
               repo: Repository = Depends(get_ready_repo), db: Session = Depends(get_db)):
    stmt = select(FileRecord).where(FileRecord.repo_id == repo.id)
    if module:
        stmt = stmt.where(FileRecord.module == module)
    if language:
        stmt = stmt.where(FileRecord.language == language)
    if q:
        stmt = stmt.where(FileRecord.path.ilike(f"%{q}%"))
    return db.scalars(stmt.order_by(FileRecord.path).limit(limit).offset(offset)).all()


@router.get("/files/{file_path:path}", response_model=FileExplanation, summary="Plain-English explanation of a file")
def explain_file(file_path: str, repo: Repository = Depends(get_ready_repo), db: Session = Depends(get_db)):
    f = db.scalar(select(FileRecord).where(FileRecord.repo_id == repo.id, FileRecord.path == file_path))
    if f is None:
        raise HTTPException(404, f"File '{file_path}' not found in index")
    symbols = db.scalars(select(Symbol).where(Symbol.repo_id == repo.id, Symbol.file_path == file_path)
                         .order_by(Symbol.line)).all()
    out_edges = db.scalars(select(ImportEdge).where(ImportEdge.repo_id == repo.id,
                                                    ImportEdge.source_path == file_path)).all()
    imports = sorted({e.target_path for e in out_edges if e.target_path})
    external = sorted({e.target for e in out_edges if not e.target_path})
    imported_by = sorted(set(db.scalars(select(ImportEdge.source_path).where(
        ImportEdge.repo_id == repo.id, ImportEdge.target_path == file_path))))

    explanation, provider = None, None
    if ai_client.enabled:
        code = read_repo_file(repo, file_path) or ""
        res = ai_client.explain_file(file_path, f.language, code,
                                     [{"name": s.name, "kind": s.kind, "signature": s.signature} for s in symbols])
        if res:
            explanation, provider = res
    if not explanation:
        parts = [f"`{file_path}` is a {f.language} file ({f.line_count} lines) in the `{f.module}` module."]
        if f.summary:
            parts.append(f.summary)
        if symbols:
            parts.append("Key definitions: " + ", ".join(f"`{s.name}`" for s in symbols[:6]) + ".")
        if imports:
            parts.append(f"It depends on {len(imports)} internal file(s): " + ", ".join(f"`{p}`" for p in imports[:5]) + ".")
        parts.append(f"It is imported by {len(imported_by)} other file(s)." if imported_by
                     else "No other file imports it (it may be an entry point or unused).")
        explanation = " ".join(parts)

    return FileExplanation(path=f.path, module=f.module, language=f.language, line_count=f.line_count,
                           summary=f.summary, explanation=explanation, used_ai=provider is not None, provider=provider,
                           symbols=[SymbolOut.model_validate(s) for s in symbols], imports=imports,
                           external_imports=external, imported_by=imported_by)


@router.get("/symbols", response_model=list[SymbolOut], summary="Search functions / classes")
def search_symbols(q: str | None = None, kind: str | None = Query(None, description="class|function|method"),
                   limit: int = Query(50, le=200), repo: Repository = Depends(get_ready_repo),
                   db: Session = Depends(get_db)):
    stmt = select(Symbol).where(Symbol.repo_id == repo.id)
    if q:
        stmt = stmt.where(Symbol.name.ilike(f"%{q}%"))
    if kind:
        stmt = stmt.where(Symbol.kind == kind)
    return db.scalars(stmt.order_by(Symbol.name).limit(limit)).all()


@router.get("/graph", response_model=Graph, summary="Dependency graph (file or module level)")
def dependency_graph(level: str = Query("module", pattern="^(file|module)$"), limit: int = Query(300, le=2000),
                     repo: Repository = Depends(get_ready_repo), db: Session = Depends(get_db)):
    files = {f.path: f for f in db.scalars(select(FileRecord).where(FileRecord.repo_id == repo.id))}
    edges = db.scalars(select(ImportEdge).where(ImportEdge.repo_id == repo.id,
                                                ImportEdge.target_path.is_not(None))).all()
    if level == "file":
        used = {e.source_path for e in edges} | {e.target_path for e in edges}
        nodes = [GraphNode(id=p, label=p.split("/")[-1], module=files[p].module, language=files[p].language)
                 for p in sorted(used) if p in files][:limit]
        ids = {n.id for n in nodes}
        out = [GraphEdge(source=e.source_path, target=e.target_path) for e in edges
               if e.source_path in ids and e.target_path in ids]
        return Graph(level=level, nodes=nodes, edges=out)
    weights: Counter = Counter()
    for e in edges:
        a, b = files[e.source_path].module, files[e.target_path].module
        if a != b:
            weights[(a, b)] += 1
    mods = sorted({m.module for m in files.values()})
    return Graph(level=level, nodes=[GraphNode(id=m, label=m) for m in mods],
                 edges=[GraphEdge(source=a, target=b, weight=w) for (a, b), w in weights.most_common()])


@router.get("/source", response_model=SourceOut, summary="Raw source of an indexed file")
def file_source(path: str, repo: Repository = Depends(get_ready_repo), db: Session = Depends(get_db)):
    f = db.scalar(select(FileRecord).where(FileRecord.repo_id == repo.id, FileRecord.path == path))
    if f is None:
        raise HTTPException(404, f"File '{path}' not found in index")
    text = read_repo_file(repo, path)
    if text is None:
        raise HTTPException(404, "Source not available on disk (repo checkout moved or deleted?)")
    lines = text.splitlines()
    cap = 3000
    return SourceOut(path=path, language=f.language, content="\n".join(lines[:cap]),
                     line_count=len(lines), truncated=len(lines) > cap)
