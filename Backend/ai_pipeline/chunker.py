"""Symbol-aware chunking into LangChain Documents: one chunk per function/method, one per class header, plus
the leftover module-level code. Files tree-sitter cannot parse fall back to line windows.

Document.metadata: file_path, start_line, end_line (1-based, inclusive), symbol_uid, label."""
from langchain_core.documents import Document

from .config import CHUNK_MAX_CHARS, MIN_CHUNK_CHARS, WINDOW_LINES, WINDOW_OVERLAP
from .parser import ParsedFile


def make_doc(path: str, start: int, end: int, content: str, uid: str | None = None, label: str = "") -> Document:
    return Document(page_content=content, metadata={"file_path": path, "start_line": start, "end_line": end,
                                                    "symbol_uid": uid, "label": label})


def embed_text(doc: Document) -> str:
    """Text that gets embedded: path + symbol name give the model useful context."""
    m = doc.metadata
    head = f"{m['file_path']} :: {m['label']}" if m.get("label") else m["file_path"]
    return f"{head}\n{doc.page_content}"


def _split_range(lines: list[str], start: int, end: int, max_chars: int = CHUNK_MAX_CHARS):
    """Yield (start, end) line ranges (1-based, inclusive) each at most ~max_chars, with small overlap."""
    i = start
    while i <= end:
        j, size = i, 0
        while j <= end and (size + len(lines[j - 1]) + 1 <= max_chars or j == i):
            size += len(lines[j - 1]) + 1
            j += 1
        yield i, j - 1
        if j > end:
            break
        i = max(i + 1, j - WINDOW_OVERLAP)


def _emit(out, path, lines, start, end, uid=None, label=""):
    if start > end:
        return
    body = "\n".join(lines[start - 1:end])
    if len(body.strip()) < MIN_CHUNK_CHARS:
        return
    for s, e in _split_range(lines, start, end):
        out.append(make_doc(path, s, e, "\n".join(lines[s - 1:e]), uid, label))


def chunk_file(path: str, text: str, parsed: ParsedFile | None) -> list[Document]:
    lines = text.split("\n")
    n = len(lines)
    out: list[Document] = []
    if parsed is None or not parsed.symbols:
        _emit_windows(out, path, lines, 1, n)
        return out
    kind = {s.uid: s.kind for s in parsed.symbols}
    covered = [False] * (n + 2)

    def mark(a, b):
        for i in range(max(1, a), min(n, b) + 1):
            covered[i] = True

    for s in parsed.symbols:
        if s.kind in ("function", "method") and kind.get(s.parent) not in ("function", "method"):
            _emit(out, path, lines, s.start_line, min(s.end_line, n), s.uid, s.qualname)
            mark(s.start_line, s.end_line)
        elif s.kind == "class":
            kids = [c.start_line for c in parsed.symbols if c.parent == s.uid]
            header_end = (min(kids) - 1) if kids else s.end_line
            _emit(out, path, lines, s.start_line, min(header_end, n), s.uid, s.qualname)
            mark(s.start_line, header_end)
    i = 1                                           # leftover module-level code
    while i <= n:
        if covered[i]:
            i += 1
            continue
        j = i
        while j + 1 <= n and not covered[j + 1]:
            j += 1
        _emit(out, path, lines, i, j, None, "module-level")
        i = j + 1
    out.sort(key=lambda c: (c.metadata["start_line"], c.metadata["end_line"]))
    return out


def _emit_windows(out, path, lines, start, end):
    i = start
    while i <= end:
        j = min(end, i + WINDOW_LINES - 1)
        body = "\n".join(lines[i - 1:j])
        if len(body.strip()) >= MIN_CHUNK_CHARS:
            for s, e in _split_range(lines, i, j):
                out.append(make_doc(path, s, e, "\n".join(lines[s - 1:e])))
        if j >= end:
            break
        i = j + 1 - WINDOW_OVERLAP
