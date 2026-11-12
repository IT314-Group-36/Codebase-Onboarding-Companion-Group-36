"""Natural-language impact analysis: "What would break if I change charge_card?" asked in the Ask box.

Pipeline (everything except the last step is deterministic, so it works without an LLM and is easy to test):
  1. detect_impact_intent: is this a "what breaks / who depends on this" question? (no extra LLM call)
  2. extract_mentions + resolve_target: find the function / file / folder the user means by matching identifiers and
     paths in the question against the indexed symbols and files (hybrid search proposes candidates when nothing is named)
  3. build_report: run the existing reverse-graph impact analysis and add call chains, tests and dependencies
  4. render_summary: plain-English answer from the report;  narrate_impact: optional LLM version of the same facts
"""
import re
from dataclasses import dataclass, field

import networkx as nx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline.graph import impact as run_impact
from ai_pipeline.graph import is_test_path
from ai_pipeline.llm import structured_chain
from app.models import File, Repository, Symbol
from app.services.explain import TargetError
from app.services.graph_service import load_graphs, resolve_symbol
from app.services.qa import NL_IMPACT_PROMPT, ImpactExplanation, LLMCallError
from app.services.retrieval import PgHybridRetriever

CAVEAT = "Static analysis: dynamic calls, reflection and string-based imports are not visible. Treat as 'likely affected'."
DEFAULT_DEPTH = 3
MAX_LISTED = 8              # items spelled out in the text summary; the JSON carries everything
LLM_LISTED = 25             # items per list handed to the LLM (it cannot open "the full list in the response")
MAX_CANDIDATES = 8


# ----------------------------------------------------------------------------- 1. intent
_CHANGE = (r"(?:chang(?:e|es|ed|ing)|modif(?:y|ies|ied|ying)|edit(?:s|ed|ing)?|renam(?:e|es|ed|ing)|delet(?:e|es|ed|ing)|"
           r"remov(?:e|es|ed|ing)|refactor(?:s|ed|ing)?|updat(?:e|es|ed|ing)|alter(?:s|ed|ing)?|rewrit(?:e|es|ing)|rewrote|"
           r"replac(?:e|es|ed|ing)|drop(?:s|ped|ping)?|deprecat(?:e|es|ed|ing)|mov(?:e|es|ed|ing)|touch(?:es|ed|ing)?|"
           r"swap(?:s|ped|ping)?|tweak(?:s|ed|ing)?|fix(?:es|ed|ing)?|rework(?:s|ed|ing)?|split(?:s|ting)?|merg(?:e|es|ed|ing))")
_CHANGE_RE = re.compile(rf"\b{_CHANGE}\b")
_IMPACT_WORDS = re.compile(r"\b(?:break\w*|broke\w*|affect\w*|impact\w*|happen\w*|depend\w*|safe\w*|else|fail\w*|stop\w*|"
                           r"risk\w*|side[- ]effects?|consequences?|ripple|cascade|regress\w*|still work|need\w* to|should i|tests?)\b")
_FORWARD = re.compile(r"\b(?:what|which)\b(?:\s+\w+){0,3}?\s+(?:does|do|did|is|are)\b.{0,60}?\b"
                      r"(?:call|calls|use|uses|import|imports|depends? on|relies on|rely on)\b")
_INTENT = [
    re.compile(r"\b(?:what|which)\b.{0,50}?\b(?:break|breaks|broken|affected|impacted)\b"),
    re.compile(r"\b(?:anything|everything|something|tests?)\b.{0,30}\b(?:break|breaks|fail|fails)\b"),
    re.compile(rf"\b(?:safe|safely|risky|dangerous)\b.{{0,30}}\b{_CHANGE}\b|\b{_CHANGE}\b.{{0,40}}\b(?:safe|safely|risky|dangerous)\b"),
    re.compile(r"\bblast radius\b|\b(?:impact|consequences?|side effects?|ripple effects?)\b.{0,15}\b(?:of|from)\b"),
    re.compile(r"\b(?:callers?|dependents?|usages?)\b.{0,6}\bof\b"),
    re.compile(r"\b(?:who|what|which|where)\b.{0,30}?\b(?:calls?|uses?|imports?|references?|depends? on|relies on|rely on)\b"),
    re.compile(r"\bwhere\b.{0,40}?\b(?:used|called|imported|referenced|invoked)\b"),
]
_CONDITIONAL_CHANGE = re.compile(rf"\b(?:if|when|after|by)\b.{{0,50}}?\b{_CHANGE}\b")
_DIRECT = re.compile(r"\b(?:direct|directly|immediate|immediately)\b")


def detect_impact_intent(question: str) -> tuple[bool, bool]:
    """Returns (is_impact_question, mentions_a_change). The second flag decides whether an unresolvable target is worth a
    clarifying answer (the user clearly wants to change *something*) or the question should fall through to plain Q&A."""
    t = " ".join(question.lower().split())
    change = bool(_CHANGE_RE.search(t))
    if _FORWARD.search(t):                                   # "what does X call?" is about X's own dependencies, not impact
        return False, change
    if any(p.search(t) for p in _INTENT):
        return True, change
    if _CONDITIONAL_CHANGE.search(t) and _IMPACT_WORDS.search(t):
        return True, change
    return False, change


# ----------------------------------------------------------------------------- 2. mentions and target resolution
_STOP = set("""the and for are how what where which does that this with from into about when who why can was were has have not you
your its there their they them than then will would should could is it of in on to a an do i we if any all else also just still
please anything everything something nothing break breaks broken happen happens affect affected affects impact impacted depend
depends depending call calls called calling use uses used using import imports imported safe safely risky function functions
method methods class classes file files module modules package folder directory code project repo repository thing things test
tests other another directly indirectly need needs check logic part parts one ones way make made get gets got see run runs
really actually code base codebase app application system software now today later first last next new old many much more
most some only even ever again yet""".split())
_SLASH_PATH = re.compile(r"(?<![\w@.-])(?:\./)?[\w@.-]+/(?:[\w@.-]+(?:/[\w@.-]+)*/?)?")     # a/b.py, src/app/, core/
_EXT = r"(?:py|js|jsx|ts|tsx|mjs|cjs|json|md|ya?ml|toml|cfg|ini|txt|html|css|sql|sh|go|rs|java|rb|php|cs)"
_FILE_NAME = re.compile(rf"(?<![\w@./-])[\w@-]+(?:\.[\w@-]+)*\.{_EXT}\b")
_FILE_EXT_END = re.compile(rf"\.{_EXT}$")
_QUOTED = re.compile(r"`([^`\n]{1,200})`|\"([^\"\n]{1,200})\"")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_ANCHOR = re.compile(rf"\b(?:{_CHANGE}|calls?|uses?|imports?|depends? on|relies on|used|called|imported|referenced)\b")
_MODULE_WORD = re.compile(r"\b(?:module|package|folder|directory|component|layer|service)\b")


@dataclass
class Mention:
    text: str
    pos: int
    is_path: bool
    quoted: bool = False
    names: list[str] = field(default_factory=list)     # lookup names, most specific first (dotted names add their last part)
    bare: bool = False                                 # all-lowercase single word ("serializer"): may be ordinary English, not an identifier


def extract_mentions(question: str) -> list[Mention]:
    """Pull candidate names and paths out of a question. Only a candidate list: the database decides what really exists."""
    found: list[Mention] = []
    work = question

    def blank(m):
        nonlocal work
        work = work[:m.start()] + " " * (m.end() - m.start()) + work[m.end():]

    for m in _QUOTED.finditer(question):                              # `name`, "name": explicit, highest confidence
        text = (m.group(1) or m.group(2)).strip().removesuffix("()").strip()
        if text and " " not in text:
            is_path = "::" not in text and ("/" in text or bool(_FILE_EXT_END.search(text)))   # "a/b.py::f" is a symbol uid
            found.append(Mention(text, m.start(), is_path, True, [text]))
        blank(m)
    for rx in (_SLASH_PATH, _FILE_NAME):
        for m in list(rx.finditer(work)):
            text = m.group(0).rstrip(".,;:?!)").removeprefix("./")
            found.append(Mention(text, m.start(), True, False, [text]))
            blank(m)
    for m in _IDENT.finditer(work):
        text = m.group(0)
        plain = "." not in text and "_" not in text and text[1:] == text[1:].lower()    # "what" or "What", not camelCase
        if len(text) < 3 or (plain and (text.lower() in _STOP or _CHANGE_RE.fullmatch(text.lower()))):
            continue
        names = [text]
        if "." in text and len(text.rsplit(".", 1)[1]) >= 3 and text.rsplit(".", 1)[1].lower() not in _STOP:
            names.append(text.rsplit(".", 1)[1])
        found.append(Mention(text, m.start(), False, False, names, plain and text.islower()))
    seen, unique = set(), []
    for m in sorted(found, key=lambda x: x.pos):
        if m.text not in seen:
            seen.add(m.text)
            unique.append(m)
    return unique[:40]


@dataclass
class Target:
    kind: str                       # symbol | file | module (a whole folder)
    label: str
    uids: list[str]
    files: list[str]
    info: dict


@dataclass
class Resolution:
    target: Target | None = None
    candidates: list[dict] = field(default_factory=list)
    message: str = ""
    also_mentioned: list[str] = field(default_factory=list)


def symbol_target(sg: nx.DiGraph, uid: str) -> Target:
    d = sg.nodes[uid]
    return Target("symbol", d["qualname"], [uid], [], {"kind": "symbol", "uid": uid, "qualname": d["qualname"], "name": d["name"],
                  "symbol_kind": d["kind"], "file_path": d["path"], "start_line": d["start_line"], "end_line": d["end_line"]})


def file_target(sg: nx.DiGraph, path: str) -> Target:
    return Target("file", path, [n for n, d in sg.nodes(data=True) if d["path"] == path], [path], {"kind": "file", "path": path})


def module_target(fg: nx.DiGraph, sg: nx.DiGraph, prefix: str, name: str | None = None) -> Target:
    prefix = prefix.rstrip("/")
    files = sorted(f for f in fg.nodes if f == prefix or f.startswith(prefix + "/"))
    inside = set(files)
    return Target("module", prefix, [n for n, d in sg.nodes(data=True) if d["path"] in inside], files,
                  {"kind": "module", "path": prefix, "name": name or prefix, "files": len(files)})


def _sym_candidate(s) -> dict:
    return {"uid": s.uid, "qualname": s.qualname, "kind": s.kind, "file_path": s.file_path}


def _match_tiers(name: str, syms: list, merge: bool = False) -> list:
    """Symbols called `name`: exact uid, then exact qualified name, then exact name, then any letter case. The first tier
    that hits wins, except with merge=True (bare words such as "the serializer"): every tier counts, so the exact-case
    function `serializer` and the class `Serializer` both stay candidates and the user is asked instead of guessed for."""
    low = name.lower()
    hits: list = []
    for pred in (lambda s: s.uid == name, lambda s: s.qualname == name, lambda s: s.name == name,
                 lambda s: s.qualname.lower() == low or s.name.lower() == low):
        hits += [s for s in syms if pred(s) and s not in hits]
        if hits and not merge:
            break
    return hits


async def _lookup_symbols(session: AsyncSession, repo_id: int, mentions: list[Mention]) -> dict[str, list]:
    named = [m for m in mentions if not m.is_path]
    raw = {n for m in named for n in m.names}
    if not raw:
        return {}
    lowered = {n.lower() for n in raw}
    rows = list((await session.execute(select(Symbol).where(
        Symbol.repo_id == repo_id,
        or_(Symbol.uid.in_(raw), func.lower(Symbol.name).in_(lowered), func.lower(Symbol.qualname).in_(lowered))).limit(500))).scalars())
    hits: dict[str, list] = {}
    for m in named:
        for n in m.names:                                              # most specific name first; stop at the first that matches
            hits[m.text] = _match_tiers(n, rows, merge=m.bare)
            if hits[m.text]:
                break
    return hits


async def _lookup_paths(session: AsyncSession, repo_id: int, fg: nx.DiGraph, m: Mention) -> tuple[list[str], str | None]:
    """(matching file paths, folder prefix). Exact path, then unique path suffix (`db.py`), then a folder holding files."""
    if m.text in fg:
        return [m.text], None
    suffix = list((await session.execute(select(File.path).where(
        File.repo_id == repo_id, File.path.endswith("/" + m.text, autoescape=True)).order_by(File.path).limit(MAX_CANDIDATES))).scalars())
    if suffix:
        return suffix, None
    prefix = m.text.rstrip("/")
    return [], (prefix if any(f.startswith(prefix + "/") for f in fg.nodes) else None)


def _module_by_name(repo: Repository, mentions: list[Mention], question: str) -> tuple[str, str] | None:
    """'the payments module': module-map names/paths, only when the question says module/package/folder/..."""
    if not _MODULE_WORD.search(question.lower()):
        return None
    mods = (repo.module_map or {}).get("modules", [])
    for m in mentions:
        if m.is_path:
            continue
        for mod in mods:
            path = mod["path"].rstrip("/")
            if m.text.lower() in (mod["name"].lower(), path.lower(), path.rsplit("/", 1)[-1].lower()):
                return path, mod["name"]
    return None


async def _retrieval_candidates(session: AsyncSession, repo_id: int, embedder, question: str) -> list[dict]:
    docs = await PgHybridRetriever(repo_id=repo_id, embeddings=embedder, k=12).ainvoke(question)
    uids = list(dict.fromkeys(d.metadata["symbol_uid"] for d in docs if d.metadata.get("symbol_uid")))[:MAX_CANDIDATES]
    if not uids:
        return []
    rows = {s.uid: s for s in (await session.execute(select(Symbol).where(Symbol.repo_id == repo_id, Symbol.uid.in_(uids)))).scalars()}
    return [_sym_candidate(rows[u]) for u in uids if u in rows]


async def resolve_target(session: AsyncSession, repo: Repository, fg: nx.DiGraph, sg: nx.DiGraph, question: str, *,
                         symbol: str | None = None, file: str | None = None, has_change: bool = False,
                         embedder=None) -> Resolution:
    """Find what the question is about. Raises TargetError for an explicit hint that does not exist."""
    if symbol:
        sym, cands = await resolve_symbol(session, repo.id, symbol)
        if sym is not None:
            return Resolution(symbol_target(sg, sym.uid))
        if not cands:
            raise TargetError(404, "No symbol matches")
        return Resolution(candidates=[_sym_candidate(c) for c in cands], message=f"`{symbol}` matches several symbols.")
    if file:
        if file not in fg:
            raise TargetError(404, "File not found")
        return Resolution(file_target(sg, file))

    mentions = extract_mentions(question)
    anchor_match = _ANCHOR.search(question.lower())
    anchor = anchor_match.start() if anchor_match else 0
    sym_hits = await _lookup_symbols(session, repo.id, mentions)
    entries = []                                                       # (pos, kind, payload, mention)
    for m in mentions:
        if m.is_path:
            files, folder = await _lookup_paths(session, repo.id, fg, m)
            if files:
                entries.append((m.pos, "file", files, m))
            elif folder:
                entries.append((m.pos, "folder", folder, m))
        elif sym_hits.get(m.text):
            entries.append((m.pos, "symbol", sym_hits[m.text], m))
    pool = [e for e in entries if e[0] >= anchor] or entries           # what comes after "change"/"calls"/... wins

    sym_e = next((e for e in pool if e[1] == "symbol"), None)
    file_e = next((e for e in pool if e[1] == "file"), None)
    folder_e = next((e for e in pool if e[1] == "folder"), None)
    chosen, others = None, []
    if sym_e:
        syms = sym_e[2]
        if file_e:                                                     # "charge_card in shop/payments.py": the file narrows the symbol
            narrowed = [s for s in syms if s.file_path in file_e[2]]
            syms = narrowed or syms
        if len(syms) == 1:
            chosen = symbol_target(sg, syms[0].uid)
        else:
            syms = sorted(syms, key=lambda s: (is_test_path(s.file_path), s.qualname, s.file_path))     # production code first
            return Resolution(candidates=[_sym_candidate(s) for s in syms[:MAX_CANDIDATES]],
                              message=f"`{sym_e[3].text}` matches several symbols.")
        others = [e[3].text for e in pool if e is not sym_e and e[1] != "file"]
    elif file_e:
        if len(file_e[2]) > 1:
            return Resolution(candidates=[{"path": p} for p in file_e[2]], message=f"`{file_e[3].text}` matches several files.")
        chosen = file_target(sg, file_e[2][0])
        others = [e[3].text for e in pool if e is not file_e]
    elif folder_e:
        mod_name = next((m["name"] for m in (repo.module_map or {}).get("modules", []) if m["path"].rstrip("/") == folder_e[2]), None)
        chosen = module_target(fg, sg, folder_e[2], mod_name)
    else:
        named = _module_by_name(repo, mentions, question)
        if named:
            chosen = module_target(fg, sg, *named)
    if chosen is not None:
        return Resolution(chosen, also_mentioned=others[:5])
    if has_change and embedder is not None:                            # "what breaks if I change the payment logic": propose candidates
        cands = await _retrieval_candidates(session, repo.id, embedder, question)
        if cands:
            return Resolution(candidates=cands, message="I could not tell which function or file you mean.")
    return Resolution()


# ----------------------------------------------------------------------------- 3. report
def _n(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _chain_names(sg: nx.DiGraph, via: list[str]) -> list[str]:
    return [sg.nodes[u]["qualname"] for u in via]


def _symbol_reason(chain: list[str], distance: int) -> str:
    if distance == 1:
        return f"calls `{chain[-1]}` directly"
    middle = " → ".join(f"`{c}`" for c in chain[1:-1])
    return f"reaches `{chain[-1]}` through {middle} ({distance} steps away)"


def _file_reason(via: list[str] | None, distance: int, syms: list[str]) -> str:
    if via:
        if distance == 1:
            return f"imports `{via[-1]}` directly"
        return f"imports `{via[1]}`, which leads to `{via[-1]}` ({distance} steps away)"
    shown = ", ".join(f"`{s}`" for s in syms[:3]) + (f" and {len(syms) - 3} more" if len(syms) > 3 else "")
    return f"contains {shown}, which {'is' if len(syms) == 1 else 'are'} affected"


def _dependencies(target: Target, sg: nx.DiGraph, fg: nx.DiGraph) -> dict:
    inside, files = set(target.uids), set(target.files)
    calls, seen = [], set()
    for uid in target.uids:
        for t in sg.successors(uid):
            if t not in inside and t not in seen:
                seen.add(t)
                d = sg.nodes[t]
                calls.append({"uid": t, "qualname": d["qualname"], "file_path": d["path"], "start_line": d["start_line"]})
    imports = sorted({dst for f in files for dst in (fg.successors(f) if f in fg else ()) if dst not in files})
    return {"calls": sorted(calls, key=lambda c: (c["file_path"], c["qualname"]))[:30], "imports": imports[:30]}


def build_report(sg: nx.DiGraph, fg: nx.DiGraph, target: Target, depth: int = DEFAULT_DEPTH) -> dict:
    res = run_impact(sg, fg, target.uids, target.files, depth, with_paths=True)
    by_file: dict[str, list[str]] = {}
    symbols = []
    for s in res["affected_symbols"]:
        chain = _chain_names(sg, s["via"])
        symbols.append({**s, "chain": chain, "reason": _symbol_reason(chain, s["distance"]), "is_test": is_test_path(s["path"])})
        by_file.setdefault(s["path"], []).append(s["qualname"])
    files = [{**f, "reason": _file_reason(f["via"], f["distance"], by_file.get(f["path"], [])), "is_test": is_test_path(f["path"])}
             for f in res["affected_files"]]
    tests = [{"path": f["path"], "reason": f["reason"]} for f in files if f["is_test"]]
    ident = {"symbol": target.info.get("uid"), "file": target.info.get("path"), "module": target.info.get("path")}[target.kind]
    report = {"target": ident, "target_info": target.info, "depth": depth, "affected_symbols": symbols, "affected_files": files,
              "affected_tests": tests, "dependencies": _dependencies(target, sg, fg),
              "totals": {"symbols": len(symbols), "files": len(files), "tests": len(tests)}}
    report["summary"] = render_summary(report)
    return report


def _describe(info: dict) -> str:
    if info["kind"] == "symbol":
        return f"`{info['qualname']}` ({info['file_path']}:{info['start_line']})"
    if info["kind"] == "file":
        return f"`{info['path']}`"
    return f"the `{info['path']}` folder ({_n(info['files'], 'file')})"


def _listed(lines: list[str], limit: int = MAX_LISTED) -> list[str]:
    out = [f"- {line}" for line in lines[:limit]]
    if len(lines) > limit:
        out.append(f"- ... and {len(lines) - limit} more (see the full list in the response)")
    return out


def render_summary(report: dict, limit: int = MAX_LISTED) -> str:
    """Deterministic plain-English answer built only from the report (used as the answer when no LLM is available).
    `limit` caps how many items each list spells out (the LLM is given a longer list than the user-facing text)."""
    info, syms, files, tests = report["target_info"], report["affected_symbols"], report["affected_files"], report["affected_tests"]
    what = _describe(info)
    if not syms and not files:
        unit = "calls it" if info["kind"] == "symbol" else "imports or calls into it"
        out = [f"Nothing else in this repository {unit} that the analysis could find, so changing {what} is unlikely to break other code here.",
               "It could still be an entry point, be used dynamically, or be used by code outside this repository."]
    else:
        direct = [s for s in syms if s["distance"] == 1]
        indirect = [s for s in syms if s["distance"] > 1]
        out = [f"Changing {what} is likely to affect {_n(len(syms), 'function')} and {_n(len(files), 'file')} "
               f"(following calls and imports up to {report['depth']} steps)."]
        for label, group in (("Directly affected", direct), ("Indirectly affected", indirect)):
            prod = [s for s in group if not s["is_test"]]
            n_test = len(group) - len(prod)                  # test functions are counted, not listed: they would bury the real callers
            if prod:
                extra_note = f", plus {_n(n_test, 'test function')}" if n_test else ""
                out += [f"{label} ({len(prod)}{extra_note}):"] + _listed(
                    [f"`{s['qualname']}` ({s['path']}:{s['start_line']}) {s['reason']}" for s in prod], limit)
            elif n_test:
                out.append(f"{label}: only {_n(n_test, 'test function')}.")
        extra = [f for f in files if f["path"] not in {s["path"] for s in syms}]
        if extra:
            out += [f"Other files that import it ({len(extra)}):"] + _listed([f"`{f['path']}` {f['reason']}" for f in extra], limit)
        out.append(("Tests that reach it: " + ", ".join(f"`{t['path']}`" for t in tests[:limit]) + ".") if tests else
                   "No test files reach it in the analysis, so check or add tests by hand before changing it.")
    deps = report["dependencies"]
    if deps["calls"]:
        out.append("For context, it relies on: " + ", ".join(f"`{c['qualname']}` ({c['file_path']})" for c in deps["calls"][:limit]) + ".")
    elif deps["imports"] and info["kind"] != "symbol":
        out.append("For context, it imports: " + ", ".join(f"`{p}`" for p in deps["imports"][:limit]) + ".")
    return "\n".join(out)


# ----------------------------------------------------------------------------- 4. LLM narration + orchestration
async def narrate_impact(llm, question: str, report: dict) -> str:
    try:
        out = await structured_chain(NL_IMPACT_PROMPT, llm, ImpactExplanation).ainvoke({
            "question": question, "target": report["target"], "facts": render_summary(report, LLM_LISTED)})
    except Exception as e:  # noqa: BLE001
        raise LLMCallError(str(e)) from e
    return out.explanation + ("\n\nSuggested checks:\n" + "\n".join(f"- {c}" for c in out.suggested_checks) if out.suggested_checks else "")


def _citations(report: dict) -> list[dict]:
    info = report["target_info"]
    cites = [{"path": info["file_path"], "start_line": info["start_line"], "end_line": info["end_line"]}] if info["kind"] == "symbol" else []
    return cites + [{"path": s["path"], "start_line": s["start_line"], "end_line": s["start_line"]}
                    for s in report["affected_symbols"] if s["distance"] == 1][:10]


async def answer_impact_question(session: AsyncSession, repo: Repository, question: str, *, symbol: str | None = None,
                                 file: str | None = None, depth: int | None = None, embedder=None, llm=None) -> dict | None:
    """Returns the /ask response for an impact question, or None when this is not one (caller falls back to normal Q&A).
    Raises TargetError when an explicit symbol/file hint does not exist."""
    is_impact, has_change = detect_impact_intent(question)
    if not is_impact:
        return None
    fg, sg = await load_graphs(session, repo.id)
    res = await resolve_target(session, repo, fg, sg, question, symbol=symbol, file=file, has_change=has_change, embedder=embedder)
    base = {"intent": "impact", "citations": [], "sources": [], "warnings": [], "caveat": CAVEAT}
    if res.target is None:
        if not res.candidates:
            return None
        picks = ", ".join(f"`{c.get('qualname') or c['path']}`" for c in res.candidates[:5])
        return {**base, "needs_clarification": True, "candidates": res.candidates, "impact": None,
                "answer": f"{res.message} Which one do you mean? Candidates: {picks}. Ask again with `symbol` (or `file`) set to your choice."}
    use_depth = depth or (1 if _DIRECT.search(question.lower()) else DEFAULT_DEPTH)
    report = build_report(sg, fg, res.target, use_depth)
    answer = report["summary"]
    if llm is not None:
        try:
            answer = await narrate_impact(llm, question, report)
        except LLMCallError as e:                                       # the structured analysis is still a complete answer
            base["warnings"].append(f"The LLM explanation is unavailable ({str(e)[:150]}); showing the structured analysis instead.")
    else:
        base["warnings"].append("No LLM API key is set (LLM_API_KEY): the answer is the structured analysis, not LLM prose.")
    if res.also_mentioned:
        base["warnings"].append("Also mentioned in the question but not analysed: " + ", ".join(res.also_mentioned) + ".")
    return {**base, "needs_clarification": False, "candidates": [], "answer": answer, "impact": report, "citations": _citations(report)}
