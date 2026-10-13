"""'What would break if I change X?' — reverse import graph + symbol usage scan."""
import re
from collections import defaultdict, deque

from sqlalchemy import or_, select

from ..models import FileRecord, ImportEdge, Repository, Symbol
from ..schemas import ImpactResponse
from .ingest import read_repo_file


def _is_test(path: str) -> bool:
    p = path.lower()
    return "test" in p.split("/")[-1] or "/tests/" in f"/{p}" or "/test/" in f"/{p}"


def analyze_impact(db, repo: Repository, target: str) -> ImpactResponse:
    target = target.strip()
    file_rec = db.scalar(select(FileRecord).where(FileRecord.repo_id == repo.id, FileRecord.path == target))
    symbol_name: str | None = None

    if file_rec:
        kind, defined_in = "file", [target]
    else:
        short = target.split(".")[-1]
        syms = db.scalars(select(Symbol).where(
            Symbol.repo_id == repo.id,
            or_(Symbol.name == target, Symbol.name.like(f"%.{short}"), Symbol.name == short))).all()
        if not syms:
            return ImpactResponse(target=target, kind="unknown", defined_in=[], directly_affected=[],
                                  transitively_affected=[], affected_tests=[], risk="none",
                                  notes="No file or symbol with that name was found in the index.")
        kind, symbol_name = "symbol", short
        defined_in = sorted({s.file_path for s in syms})

    reverse: dict[str, set[str]] = defaultdict(set)
    for e in db.scalars(select(ImportEdge).where(ImportEdge.repo_id == repo.id, ImportEdge.target_path.is_not(None))):
        reverse[e.target_path].add(e.source_path)

    importers = {src for d in defined_in for src in reverse.get(d, set())} - set(defined_in)

    if symbol_name:
        pat = re.compile(rf"\b{re.escape(symbol_name)}\b")
        direct = {p for p in importers if (txt := read_repo_file(repo, p)) and pat.search(txt)}
        maybe = importers - direct
    else:
        direct, maybe = set(importers), set()

    seen = set(defined_in) | direct | maybe
    queue, transitive = deque(direct | maybe), set()
    while queue:
        cur = queue.popleft()
        for nxt in reverse.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                transitive.add(nxt)
                queue.append(nxt)
    transitive |= maybe

    total = len(direct) + len(transitive)
    risk = "none" if total == 0 else "low" if total <= 2 else "medium" if total <= 8 else "high"
    everything = direct | transitive
    notes = (f"{len(direct)} file(s) use `{symbol_name or target}` directly; {len(transitive)} more depend on them "
             "indirectly. Based on static imports — dynamic imports and runtime wiring are not detected.")
    return ImpactResponse(target=target, kind=kind, defined_in=defined_in, directly_affected=sorted(direct),
                          transitively_affected=sorted(transitive),
                          affected_tests=sorted(p for p in everything if _is_test(p)), risk=risk, notes=notes)
