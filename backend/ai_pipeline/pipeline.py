"""Blocking analysis of one checked-out repo: scan -> stack -> parse -> graphs -> rank -> chunk.

No DB, no network, no LLM: easy to unit test and safe to run in a worker thread."""
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
from langchain_core.documents import Document

from .chunker import chunk_file
from .config import MAX_TOTAL_BYTES, SKIP_NAMES, SKIP_SUFFIXES
from .graph import build_graphs, rank_files
from .parser import ParsedFile, parse_file
from .repo import scan_files
from .secrets import redact_secrets
from .stack_detector import detect_tech_stack


@dataclass
class Analysis:
    all_files: list[str]
    safe_files: list[str]
    tech_stack: dict
    parsed: dict[str, ParsedFile]
    file_graph: nx.DiGraph
    symbol_graph: nx.DiGraph
    chunks: list[Document]
    report: dict = field(default_factory=dict)
    file_sizes: dict = field(default_factory=dict)


def _read_text(path: Path, max_bytes: int):
    """Returns (text, None) or (None, reason_skipped)."""
    if path.name in SKIP_NAMES or path.name.lower().endswith(SKIP_SUFFIXES):
        return None, "lockfile/minified/binary-type"
    if path.stat().st_size > max_bytes:
        return None, "too large"
    raw = path.read_bytes()
    if b"\x00" in raw[:1024]:
        return None, "binary"
    text = raw.decode("utf-8", errors="ignore")
    return (text, None) if text.strip() else (None, "empty")


def analyze_checkout(root, *, max_chunks: int = 5000, max_file_bytes: int = 200_000) -> Analysis:
    root = Path(root)
    all_files, safe_files = scan_files(root)
    tech = detect_tech_stack(root, all_files)
    sizes = {}
    for rel in all_files:
        try:
            sizes[rel] = (root / rel).stat().st_size
        except OSError:
            sizes[rel] = 0

    texts: dict[str, str] = {}
    skipped, redactions, total = Counter(), 0, 0
    for rel in safe_files:
        if total >= MAX_TOTAL_BYTES:
            skipped["repo size cap reached"] += 1
            continue
        try:
            text, reason = _read_text(root / rel, max_file_bytes)
        except OSError:
            skipped["unreadable"] += 1
            continue
        if reason:
            skipped[reason] += 1
            continue
        text, n = redact_secrets(text)
        redactions += n
        total += len(text)
        texts[rel] = text

    parsed = {}
    for rel, text in texts.items():
        pf = parse_file(rel, text)
        if pf is not None:
            parsed[rel] = pf
    fg, sg = build_graphs(parsed, all_files)

    scores = rank_files(list(texts), fg)
    chunks, dropped = [], []
    for rel in sorted(texts, key=lambda f: -scores[f]):       # important files first, never random sampling
        cs = chunk_file(rel, texts[rel], parsed.get(rel))
        if len(chunks) + len(cs) > max_chunks:
            dropped.append(rel)
            continue
        chunks += cs
    if not chunks:
        raise RuntimeError("No embeddable text files found in this repository.")

    report = {
        "files": len(all_files), "sensitive_files": len(all_files) - len(safe_files),
        "files_read": len(texts), "files_skipped": dict(skipped), "parsed_files": len(parsed),
        "parse_errors": sum(1 for p in parsed.values() if p.parse_error),
        "symbols": sg.number_of_nodes(), "import_edges": fg.number_of_edges(), "call_edges": sg.number_of_edges(),
        "chunks": len(chunks), "files_dropped_by_budget": len(dropped), "dropped_examples": dropped[:10],
        "secrets_redacted": redactions,
    }
    return Analysis(all_files, safe_files, tech, parsed, fg, sg, chunks, report, sizes)
