"""Plain-English explanations of files, functions and modules.

Relationships ("this file uses X and is used by Y") are computed from the stored import/call graphs, so they are always
available and never invented. The LLM only writes the beginner-friendly prose around those facts; its output is
validated (unknown symbol names are dropped) and cached per repo. The cache is cleared on reindex and also ignored when
its commit_sha no longer matches the repo's.
"""
from collections import defaultdict

import networkx as nx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline.graph import module_of
from ai_pipeline.llm import structured_chain
from app.models import Chunk, Explanation, File, Repository
from app.services.graph_service import load_graphs, resolve_symbol
from app.services.qa import (FILE_EXPLAIN_PROMPT, SYMBOL_EXPLAIN_PROMPT, FileExplanation, LLMCallError,
                             SymbolExplanation)

RELATION_CAVEAT = ("Relationships come from static analysis of imports and calls inside this repository: dynamic calls, "
                   "reflection, string-based imports and third-party libraries are not visible.")
SENTENCE_NAMES = 5          # names spelled out in a sentence; the JSON lists carry everything (up to MAX_ITEMS)
MAX_ITEMS = 50
CODE_CHARS_FILE = 7000
CODE_CHARS_SYMBOL = 5000


class TargetError(Exception):
    """The file/symbol could not be resolved. The API turns it into an HTTP error with this status and detail."""

    def __init__(self, status: int, detail):
        super().__init__(str(detail))
        self.status, self.detail = status, detail


# ----------------------------------------------------------------------------- wording helpers
def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _names(items: list[str], tick: bool = True, limit: int = SENTENCE_NAMES) -> str:
    parts = [f"`{i}`" if tick else i for i in items[:limit]]
    if len(items) > limit:
        parts.append(f"{len(items) - limit} more")
    return _join(parts)


def _sym_ref(sg: nx.DiGraph, uid: str) -> dict:
    d = sg.nodes[uid]
    return {"uid": uid, "qualname": d["qualname"], "kind": d["kind"], "file_path": d["path"], "start_line": d["start_line"]}


def module_for(repo: Repository, path: str) -> dict | None:
    mods = (repo.module_map or {}).get("modules", [])
    best = module_of(path, [m["path"] for m in mods])
    for m in mods:
        if m["path"].rstrip("/") == best:
            return {"name": m["name"], "path": m["path"], "purpose": m.get("purpose", "")}
    return None


# ----------------------------------------------------------------------------- relationships (deterministic)
def file_relationships(path: str, fg: nx.DiGraph, sg: nx.DiGraph) -> dict:
    uses = sorted(fg.successors(path)) if path in fg else []
    used_by = sorted(fg.predecessors(path)) if path in fg else []
    own = sorted(((d["start_line"], uid) for uid, d in sg.nodes(data=True) if d["path"] == path))
    calls_into, called_from = defaultdict(list), defaultdict(list)
    symbols = []
    for _, uid in own:
        d = sg.nodes[uid]
        symbols.append({"uid": uid, "qualname": d["qualname"], "kind": d["kind"], "start_line": d["start_line"],
                        "end_line": d["end_line"], "calls": sg.out_degree(uid), "called_by": sg.in_degree(uid)})
        for t in sg.successors(uid):
            if sg.nodes[t]["path"] != path:
                calls_into[sg.nodes[t]["path"]].append({"from": d["qualname"], "to": sg.nodes[t]["qualname"]})
        for c in sg.predecessors(uid):
            if sg.nodes[c]["path"] != path:
                called_from[sg.nodes[c]["path"]].append({"from": sg.nodes[c]["qualname"], "to": d["qualname"]})

    def pack(m: dict) -> list[dict]:
        return [{"path": p, "calls": v[:10]} for p, v in sorted(m.items())][:MAX_ITEMS]

    return {"uses": uses[:MAX_ITEMS], "used_by": used_by[:MAX_ITEMS], "uses_total": len(uses), "used_by_total": len(used_by),
            "calls_into": pack(calls_into), "called_from": pack(called_from), "symbols": symbols[:MAX_ITEMS],
            "symbols_total": len(symbols)}


def file_sentence(path: str, rel: dict) -> str:
    def listed(items, total):
        parts = [f"`{i}`" for i in items[:SENTENCE_NAMES]]
        if total > len(parts):
            parts.append(f"{total - len(parts)} more")
        return _join(parts)
    first = f"uses {listed(rel['uses'], rel['uses_total'])}" if rel["uses"] else "does not import any other file in this repository"
    second = (f"is used by {listed(rel['used_by'], rel['used_by_total'])}" if rel["used_by"]
              else "is not imported by any other file we could detect (it may be an entry point or a script)")
    return f"`{path}` {first}, and {second}."


def symbol_relationships(uid: str, sg: nx.DiGraph) -> dict:
    calls = [_sym_ref(sg, t) for t in sorted(sg.successors(uid))]
    called_by = [_sym_ref(sg, c) for c in sorted(sg.predecessors(uid))]
    return {"calls": calls[:MAX_ITEMS], "called_by": called_by[:MAX_ITEMS], "calls_total": len(calls),
            "called_by_total": len(called_by)}


def symbol_sentence(qualname: str, rel: dict) -> str:
    def refs(items, total):
        parts = [f"`{i['qualname']}` ({i['file_path']})" for i in items[:SENTENCE_NAMES]]
        if total > len(parts):
            parts.append(f"{total - len(parts)} more")
        return _join(parts)
    first = f"calls {refs(rel['calls'], rel['calls_total'])}" if rel["calls"] else "does not call any other function in this repository"
    second = (f"is called by {refs(rel['called_by'], rel['called_by_total'])}" if rel["called_by"]
              else "is not called by any other function we could detect (it may be an entry point, a callback or unused)")
    return f"`{qualname}` {first}, and {second}."


def enrich_modules(modules: list[dict], graph: dict) -> list[dict]:
    """Add depends_on / used_by / relationship_summary to every module of the map (additive: existing keys untouched)."""
    outs, ins = defaultdict(list), defaultdict(list)
    label = {n["id"]: n["label"] for n in graph["nodes"]}
    for e in graph["edges"]:
        outs[e["source"]].append({"path": e["target"], "name": label.get(e["target"], e["target"]), "links": e["weight"]})
        ins[e["target"]].append({"path": e["source"], "name": label.get(e["source"], e["source"]), "links": e["weight"]})
    result = []
    for m in modules:
        mid = m["path"].rstrip("/")
        deps, users = outs.get(mid, []), ins.get(mid, [])
        first = f"uses {_names([d['name'] for d in deps], tick=False)}" if deps else "does not depend on any other module"
        second = f"is used by {_names([u['name'] for u in users], tick=False)}" if users else "is not used by any other module"
        result.append({**m, "depends_on": deps, "used_by": users,
                       "relationship_summary": f"The {m['name']} module {first}, and {second}."})
    return result


# ----------------------------------------------------------------------------- source text from stored chunks
def assemble_source(rows, lo: int | None, hi: int | None, limit: int) -> str:
    """Stitch stored chunks back into source text: overlapping windows are de-duplicated, gaps marked, size capped."""
    out, last, size = [], 0, 0
    for start, _end, content in rows:
        for n, line in enumerate(content.split("\n"), start):
            if n <= last or (lo is not None and n < lo) or (hi is not None and n > hi):
                continue
            if last and n > last + 1:
                out.append("...")
            out.append(line)
            last, size = n, size + len(line) + 1
            if size > limit:
                out.append("... (truncated)")
                return "\n".join(out)
    return "\n".join(out)


async def load_source(session: AsyncSession, repo_id: int, path: str, lo: int | None = None, hi: int | None = None,
                      limit: int = CODE_CHARS_FILE) -> str:
    stmt = (select(Chunk.start_line, Chunk.end_line, Chunk.content)
            .where(Chunk.repo_id == repo_id, Chunk.file_path == path).order_by(Chunk.start_line))
    if lo is not None and hi is not None:
        stmt = stmt.where(Chunk.end_line >= lo, Chunk.start_line <= hi)
    return assemble_source((await session.execute(stmt)).all(), lo, hi, limit)


# ----------------------------------------------------------------------------- cache
async def _cache_get(session: AsyncSession, repo: Repository, kind: str, target: str) -> dict | None:
    row = (await session.execute(select(Explanation).where(
        Explanation.repo_id == repo.id, Explanation.kind == kind, Explanation.target == target))).scalar_one_or_none()
    return row.payload if row is not None and row.commit_sha == repo.commit_sha else None   # stale (reindexed) = miss


async def _cache_put(session: AsyncSession, repo: Repository, kind: str, target: str, payload: dict) -> None:
    stmt = pg_insert(Explanation).values(repo_id=repo.id, kind=kind, target=target, commit_sha=repo.commit_sha, payload=payload)
    await session.execute(stmt.on_conflict_do_update(constraint="uq_explanations_repo_kind_target",
                                                     set_={"commit_sha": repo.commit_sha, "payload": payload}))
    await session.commit()


# ----------------------------------------------------------------------------- LLM
def _project_context(repo: Repository) -> str:
    s, mm = repo.summary or {}, repo.module_map or {}
    text = s.get("one_line") or mm.get("project_summary") or "(no project summary available)"
    if s.get("description"):
        text += " " + s["description"][:400]
    return text


def _relationships_text(kind: str, rel: dict, sentence: str) -> str:
    lines = [sentence]
    if kind == "file":
        lines += [f"Uses (imports): {', '.join(rel['uses']) or '(none)'}", f"Used by (imported by): {', '.join(rel['used_by']) or '(none)'}"]
        lines += [f"Calls into {c['path']}: " + "; ".join(f"{x['from']} -> {x['to']}" for x in c["calls"]) for c in rel["calls_into"][:10]]
        lines += [f"Called from {c['path']}: " + "; ".join(f"{x['from']} -> {x['to']}" for x in c["calls"]) for c in rel["called_from"][:10]]
    else:
        lines += [f"Calls: {', '.join(c['qualname'] + ' (' + c['file_path'] + ')' for c in rel['calls'][:20]) or '(none)'}",
                  f"Called by: {', '.join(c['qualname'] + ' (' + c['file_path'] + ')' for c in rel['called_by'][:20]) or '(none)'}"]
    return "\n".join(lines)


async def _generate_file(llm, repo, path, rel, sentence, code) -> tuple[dict, list[str]]:
    symbols = "\n".join(f"- {s['qualname']} ({s['kind']}, lines {s['start_line']}-{s['end_line']})" for s in rel["symbols"][:60]) or "(none parsed)"
    mod = module_for(repo, path)
    try:
        raw = await structured_chain(FILE_EXPLAIN_PROMPT, llm, FileExplanation).ainvoke({
            "project": _project_context(repo), "path": path, "relationships": _relationships_text("file", rel, sentence),
            "module": f"{mod['name']}: {mod['purpose']}" if mod else "(not part of a detected module)",
            "symbols": symbols, "code": code})
    except Exception as e:  # noqa: BLE001
        raise LLMCallError(str(e)) from e
    by_name = {}
    for s in rel["symbols"]:
        by_name.setdefault(s["qualname"], s)
        by_name.setdefault(s["uid"].split("::")[-1].split(".")[-1], s)
    notes, seen, dropped = [], set(), 0
    for n in raw.key_symbols:
        s = by_name.get(n.name)
        if s is None:
            dropped += 1                                    # the LLM named something that is not in this file
        elif s["uid"] not in seen:
            seen.add(s["uid"])
            notes.append({"uid": s["uid"], "name": s["qualname"], "start_line": s["start_line"], "note": n.note})
    warnings = [f"dropped {dropped} unknown symbol name(s) from the LLM output"] if dropped else []
    return {"summary": raw.summary, "explanation": raw.explanation, "key_symbols": notes[:8], "how_it_fits": raw.how_it_fits}, warnings


async def _generate_symbol(llm, repo, sym, rel, sentence, code) -> dict:
    mod = module_for(repo, sym.file_path)
    try:
        raw = await structured_chain(SYMBOL_EXPLAIN_PROMPT, llm, SymbolExplanation).ainvoke({
            "project": _project_context(repo), "target": sym.qualname, "kind": sym.kind, "path": sym.file_path,
            "signature": sym.signature or "(not available)", "relationships": _relationships_text("symbol", rel, sentence),
            "module": f"{mod['name']}: {mod['purpose']}" if mod else "(not part of a detected module)", "code": code})
    except Exception as e:  # noqa: BLE001
        raise LLMCallError(str(e)) from e
    return {"summary": raw.summary, "explanation": raw.explanation, "inputs_outputs": raw.inputs_outputs,
            "how_it_fits": raw.how_it_fits}


# ----------------------------------------------------------------------------- entry point
async def explain_target(session: AsyncSession, repo: Repository, llm, *, file: str | None = None,
                         symbol: str | None = None, refresh: bool = False) -> dict:
    """Explain one file or one symbol. Raises TargetError (404/409) or LLMCallError (502)."""
    fg, sg = await load_graphs(session, repo.id)
    warnings: list[str] = []
    if file is not None:
        row = (await session.execute(select(File).where(File.repo_id == repo.id, File.path == file))).scalar_one_or_none()
        if row is None:
            raise TargetError(404, "File not found")
        kind, target, rel = "file", file, file_relationships(file, fg, sg)
        sentence = file_sentence(file, rel)
        head = {"path": file, "language": row.language}
        module, sensitive = module_for(repo, file), row.sensitive
        lo = hi = sym = None
    else:
        sym, candidates = await resolve_symbol(session, repo.id, symbol)
        if sym is None:
            if not candidates:
                raise TargetError(404, "No symbol matches")
            raise TargetError(409, {"message": "Ambiguous symbol; pass an exact uid",
                                    "candidates": [{"uid": m.uid, "file_path": m.file_path, "kind": m.kind} for m in candidates]})
        kind, target, rel = "symbol", sym.uid, symbol_relationships(sym.uid, sg)
        sentence = symbol_sentence(sym.qualname, rel)
        head = {"uid": sym.uid, "name": sym.name, "qualname": sym.qualname, "symbol_kind": sym.kind, "file_path": sym.file_path,
                "start_line": sym.start_line, "end_line": sym.end_line, "signature": sym.signature}
        module, sensitive, lo, hi = module_for(repo, sym.file_path), False, sym.start_line, sym.end_line

    explanation, source = None, "none"
    if sensitive:
        warnings.append("Contents of sensitive files are never read, so only relationships are shown.")
    else:
        code = await load_source(session, repo.id, file or sym.file_path, lo, hi,
                                 CODE_CHARS_FILE if kind == "file" else CODE_CHARS_SYMBOL)
        cached = None if refresh else await _cache_get(session, repo, kind, target)
        if cached is not None:
            explanation, source = cached, "cache"
        elif not code.strip():
            warnings.append("No indexed text for this target, so only relationships are shown.")
        elif llm is None:
            warnings.append("No LLM API key is set (LLM_API_KEY): showing relationships only.")
        else:
            if kind == "file":
                explanation, w = await _generate_file(llm, repo, file, rel, sentence, code)
                warnings += w
            else:
                explanation = await _generate_symbol(llm, repo, sym, rel, sentence, code)
            await _cache_put(session, repo, kind, target, explanation)
            source = "llm"
    return {"kind": kind, "target": target, **head, "module": module, "relationship_summary": sentence,
            "relationships": rel, "explanation": explanation, "source": source, "warnings": warnings,
            "caveat": RELATION_CAVEAT}
