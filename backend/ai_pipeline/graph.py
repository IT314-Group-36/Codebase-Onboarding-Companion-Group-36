"""Import/call graphs (NetworkX), file ranking, graph facts for the LLM, and impact analysis.

All results are static-analysis approximations: dynamic dispatch, reflection and string-based
imports are invisible. The API labels impact results as "likely affected" for that reason.
"""
import posixpath
from collections import defaultdict

import networkx as nx

from .parser import ParsedFile

JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
ENTRY_STEMS = {"main", "app", "index", "server", "cli", "manage", "wsgi", "asgi", "__main__", "run"}


def _py_keys(path: str) -> list[str]:
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return [".".join(parts[i:]) for i in range(len(parts))] if parts else []


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a.split("/")[:-1], b.split("/")[:-1]):
        if x != y:
            break
        n += 1
    return n


class Resolver:
    """Maps an import specifier written in a file to files inside the repo (externals -> [])."""

    def __init__(self, files: list[str]):
        self.files = set(files)
        self.py_index: dict[str, list[str]] = defaultdict(list)
        for f in files:
            if f.endswith(".py"):
                for key in _py_keys(f):
                    self.py_index[key].append(f)

    def resolve(self, importer: str, spec: str, lang: str) -> list[str]:
        if not spec:
            return []
        return self._py(importer, spec) if lang == "python" else self._js(importer, spec)

    def _py(self, importer, spec):
        if spec.startswith("."):
            level = len(spec) - len(spec.lstrip("."))
            rest = spec[level:]
            base = importer.split("/")[:-1]
            if level > 1:
                base = base[:-(level - 1)] if len(base) >= level - 1 else []
            parts = base + (rest.split(".") if rest else [])
            stem = "/".join(parts)
            cands = [f"{stem}.py", f"{stem}/__init__.py"] if stem else ["__init__.py"]
            return [c for c in cands if c in self.files][:1]
        cands = self.py_index.get(spec, [])
        if not cands:
            return []
        return [max(cands, key=lambda c: (_common_prefix(c, importer), -len(c)))]

    def _js(self, importer, spec):
        if spec.startswith("."):
            bases = [posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))]
        elif spec.startswith(("@/", "~/")):
            bases = [f"src/{spec[2:]}", spec[2:]]
        else:
            return []
        for base in bases:
            if base.startswith(".."):
                continue
            stripped = base.rsplit(".", 1)[0] if base.endswith((".js", ".jsx", ".mjs")) else base
            cands = [base] + [stripped + e for e in JS_EXTS] + [f"{base}{e}" for e in JS_EXTS] \
                    + [f"{base}/index{e}" for e in JS_EXTS]
            for c in cands:
                if c in self.files:
                    return [c]
        return []


def _targets(pf, sym, name, obj, bindings, by_file, by_name, imported):
    if obj in ("self", "cls", "this"):
        same = by_file[pf.path].get(name, [])
        if "." in sym.qualname:
            cls_q = sym.qualname.rsplit(".", 1)[0]
            pref = [s for s in same if s.qualname == f"{cls_q}.{name}"]
            if pref:
                return pref
        return same
    b = bindings.get(pf.path, {})
    if obj not in (None, "?") and obj in b:                      # module alias: api.get()
        sym_files, mod_files, _ = b[obj]
        return [s for f in (mod_files or sym_files) for s in by_file[f].get(name, [])]
    if obj is None and name in b:                                # imported name: thing()
        sym_files, _, orig = b[name]
        target = name if orig in ("*", "default") else orig
        hits = [s for f in sym_files for s in by_file[f].get(target, [])]
        if hits:
            return hits
    local = by_file[pf.path].get(name, [])
    if local:
        return local
    imp = [s for f in imported.get(pf.path, ()) for s in by_file[f].get(name, [])]
    if imp:
        return imp
    if obj is None:                                              # global fallback only for plain calls
        g = by_name.get(name, [])
        if len(g) == 1:
            return g
    return []


def build_graphs(parsed: dict[str, ParsedFile], all_files: list[str]) -> tuple[nx.DiGraph, nx.DiGraph]:
    """Returns (file_graph, symbol_graph). file_graph: A -> B means A imports B.
    symbol_graph: X -> Y means X calls Y."""
    res = Resolver(all_files)
    fg = nx.DiGraph()
    fg.add_nodes_from(all_files)
    bindings: dict[str, dict] = {}
    for pf in parsed.values():
        for spec in pf.imports:
            for dst in res.resolve(pf.path, spec, pf.language):
                if dst != pf.path:
                    fg.add_edge(pf.path, dst, kind="imports")
        b = {}
        for local, (spec, orig) in pf.bindings.items():
            sym_files = res.resolve(pf.path, spec, pf.language)
            if pf.language == "python" and orig not in ("*", "default"):
                sub = spec + orig if spec.endswith(".") else f"{spec}.{orig}"
                mod_files = res.resolve(pf.path, sub, pf.language)
            else:
                mod_files = sym_files if orig in ("*", "default") else []
            b[local] = (sym_files, mod_files, orig)
        bindings[pf.path] = b

    sg = nx.DiGraph()
    by_name: dict[str, list] = defaultdict(list)
    by_file: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for pf in parsed.values():
        for s in pf.symbols:
            sg.add_node(s.uid, path=s.path, name=s.name, qualname=s.qualname, kind=s.kind,
                        start_line=s.start_line, end_line=s.end_line)
            by_name[s.name].append(s)
            by_file[pf.path][s.name].append(s)
    imported = {p: set(fg.successors(p)) for p in parsed}
    for pf in parsed.values():
        for sym in pf.symbols:
            for name, obj in sym.calls:
                for t in _targets(pf, sym, name, obj, bindings, by_file, by_name, imported):
                    if t.uid != sym.uid:
                        sg.add_edge(sym.uid, t.uid, kind="calls")
    return fg, sg


# ----------------------------------------------------------------------------- ranking & facts
def is_test_path(path: str) -> bool:
    low = path.lower()
    base = posixpath.basename(low)
    return (any(seg in ("tests", "test", "__tests__", "spec", "specs") for seg in low.split("/")[:-1])
            or base.startswith("test_") or ".test." in base or ".spec." in base or base.endswith("_test.py"))


def rank_files(files: list[str], fg: nx.DiGraph) -> dict[str, float]:
    """Higher = more important to keep when the chunk budget is limited."""
    scores = {}
    for f in files:
        base = posixpath.basename(f).lower()
        stem = base.rsplit(".", 1)[0]
        depth = f.count("/")
        s = -1.5 * depth + min(40, 5 * (fg.in_degree(f) if f in fg else 0))
        if depth == 0 and base.startswith("readme"):
            s += 50
        if stem in ENTRY_STEMS:
            s += 20
        if is_test_path(f):
            s -= 15
        if base.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".java", ".go", ".rs", ".rb", ".php", ".cs")):
            s += 10
        elif base.endswith(".md"):
            s += 5
        elif base.endswith((".json", ".yaml", ".yml", ".csv", ".txt", ".xml")):
            s -= 5
        scores[f] = s
    return scores


def folder_of(path: str, depth: int = 2) -> str:
    parts = path.split("/")[:-1][:depth]
    return "/".join(parts) if parts else "."


def graph_facts(files: list[str], fg: nx.DiGraph, top: int = 10) -> dict:
    """Deterministic structure facts handed to the LLM so it is not guessing from names alone."""
    hubs = sorted((f for f in fg.nodes if fg.in_degree(f) > 0), key=lambda f: -fg.in_degree(f))[:top]
    entry = [f for f in files if f in fg and fg.in_degree(f) == 0 and fg.out_degree(f) > 0
             and not is_test_path(f)]
    entry.sort(key=lambda f: (posixpath.basename(f).rsplit(".", 1)[0].lower() not in ENTRY_STEMS, f.count("/"), f))
    weights: dict[tuple, int] = defaultdict(int)
    for a, b in fg.edges:
        fa, fb = folder_of(a), folder_of(b)
        if fa != fb:
            weights[(fa, fb)] += 1
    folder_edges = sorted(weights.items(), key=lambda kv: -kv[1])[:25]
    return {"hubs": [(h, fg.in_degree(h)) for h in hubs], "entry_candidates": entry[:top],
            "folder_edges": [(a, b, w) for (a, b), w in folder_edges]}


def facts_text(facts: dict) -> str:
    lines = ["Most-imported files (file, imported_by_count):"]
    lines += [f"  {f} ({n})" for f, n in facts["hubs"]] or ["  (none detected)"]
    lines.append("Likely entry points (not imported by other files):")
    lines += [f"  {f}" for f in facts["entry_candidates"]] or ["  (none detected)"]
    lines.append("Folder dependencies (from -> to, number of imports):")
    lines += [f"  {a} -> {b} ({w})" for a, b, w in facts["folder_edges"]] or ["  (none detected)"]
    return "\n".join(lines)


def module_of(path: str, module_paths: list[str]) -> str | None:
    """Longest module path that contains this file."""
    best = None
    for mp in module_paths:
        mp_clean = mp.rstrip("/")
        if (path == mp_clean or path.startswith(mp_clean + "/")) and (best is None or len(mp_clean) > len(best)):
            best = mp_clean
    return best


def module_graph(modules: list[dict], file_edges: list[tuple[str, str]]) -> dict:
    """Aggregate file imports into module-to-module edges for the visual map (React Flow)."""
    paths = [m["path"] for m in modules]
    weights: dict[tuple, int] = defaultdict(int)
    for a, b in file_edges:
        ma, mb = module_of(a, paths), module_of(b, paths)
        if ma and mb and ma != mb:
            weights[(ma, mb)] += 1
    nodes = [{"id": m["path"].rstrip("/"), "label": m["name"], "purpose": m.get("purpose", "")} for m in modules]
    edges = [{"source": a, "target": b, "weight": w} for (a, b), w in sorted(weights.items(), key=lambda kv: -kv[1])]
    return {"nodes": nodes, "edges": edges}


# ----------------------------------------------------------------------------- impact analysis
def _reverse_chains(g: nx.DiGraph, start: str, cutoff: int) -> dict[str, list[str]]:
    """Breadth-first walk against the edge direction. Returns node -> [node, ..., start]: the chain along the real edges
    (caller -> ... -> start). Neighbours are visited in sorted order, so the chain shown is the same on every run."""
    chains = {start: [start]}
    frontier = [start]
    for _ in range(cutoff):
        nxt = []
        for cur in frontier:
            for n in sorted(g.predecessors(cur)):
                if n not in chains:
                    chains[n] = [n] + chains[cur]
                    nxt.append(n)
        frontier = nxt
    return chains


def impact(sg: nx.DiGraph, fg: nx.DiGraph, symbol_uids: list[str], target_files: list[str], depth: int = 3,
           with_paths: bool = False) -> dict:
    """Reverse traversal: who (transitively) calls the symbols / imports the files.
    with_paths=True adds a "via" chain to every result (affected -> ... -> target) so the answer can say WHY it is affected;
    without it the output is exactly what Sprint 1 returned."""
    dist: dict[str, int] = {}
    via: dict[str, list[str]] = {}
    rev = sg.reverse(copy=False)
    for uid in sorted(symbol_uids) if with_paths else symbol_uids:
        if uid not in sg:
            continue
        if with_paths:
            found = {n: (len(c) - 1, c) for n, c in _reverse_chains(sg, uid, depth).items()}
        else:
            found = {n: (d, None) for n, d in nx.single_source_shortest_path_length(rev, uid, cutoff=depth).items()}
        for node, (d, chain) in found.items():
            if node not in symbol_uids and (node not in dist or d < dist[node]):
                dist[node], via[node] = d, chain
    fdist: dict[str, int] = {}
    fvia: dict[str, list[str]] = {}
    frev = fg.reverse(copy=False)
    for f in sorted(target_files) if with_paths else target_files:
        if f not in fg:
            continue
        if with_paths:
            found = {n: (len(c) - 1, c) for n, c in _reverse_chains(fg, f, depth).items()}
        else:
            found = {n: (d, None) for n, d in nx.single_source_shortest_path_length(frev, f, cutoff=depth).items()}
        for node, (d, chain) in found.items():
            if node not in target_files and (node not in fdist or d < fdist[node]):
                fdist[node], fvia[node] = d, chain
    affected_symbols = [{"uid": u, **{k: sg.nodes[u][k] for k in ("path", "name", "qualname", "kind", "start_line")},
                         "distance": d, **({"via": via[u]} if with_paths else {})}
                        for u, d in sorted(dist.items(), key=lambda kv: (kv[1], kv[0]))]
    for s in affected_symbols:      # files that hold affected symbols are affected too (no import chain: via is None)
        if s["path"] not in fdist and s["path"] not in target_files:
            fdist[s["path"]], fvia[s["path"]] = s["distance"], None
    affected_files = [{"path": p, "distance": d, **({"via": fvia[p]} if with_paths else {})}
                      for p, d in sorted(fdist.items(), key=lambda kv: (kv[1], kv[0]))]
    return {"affected_symbols": affected_symbols, "affected_files": affected_files}
