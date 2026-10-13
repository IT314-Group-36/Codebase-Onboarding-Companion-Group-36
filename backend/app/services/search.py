"""Natural-language question answering over the code index (keyword/symbol based)."""
import re

from sqlalchemy import or_, select

from ..models import FileRecord, Symbol
from ..schemas import SourceRef
from .ai_client import ai_client

STOP = {"the", "and", "for", "where", "what", "how", "does", "this", "that", "with", "are", "is",
        "in", "of", "to", "a", "an", "do", "handled", "handle", "code", "logic", "file", "files",
        "which", "who", "can", "i", "find", "located", "implemented", "work", "works", "used",
        "from", "when", "why", "about", "into", "show", "tell", "me", "my", "our", "there"}


def stem(word: str) -> str:
    if word.endswith(("ss", "is", "us")):  # analysis, class, status
        return word
    for suf in ("ing", "ed", "s"):
        if word.endswith(suf) and len(word) - len(suf) >= 4:
            return word[: -len(suf)]
    return word


def tokenize(question: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return list(dict.fromkeys(stem(w) for w in words if w not in STOP and len(w) > 2))


def search_repo(db, repo_id: int, question: str, limit: int = 8) -> list[SourceRef]:
    tokens = tokenize(question)
    if not tokens:
        return []
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    first_line: dict[str, int] = {}

    credited: set[tuple[str, str, str]] = set()

    def bump(path: str, pts: float, reason: str, line: int | None = None, token: str = "", kind: str = ""):
        if token:  # each token earns each kind of match at most once per file
            if (path, token, kind) in credited:
                if line and path not in first_line:
                    first_line[path] = line
                return
            credited.add((path, token, kind))
        scores[path] = scores.get(path, 0) + pts
        if reason not in reasons.setdefault(path, []):
            reasons[path].append(reason)
        if line and path not in first_line:
            first_line[path] = line

    for t in tokens:
        like = f"%{t}%"
        for f in db.scalars(select(FileRecord).where(
                FileRecord.repo_id == repo_id,
                or_(FileRecord.path.ilike(like), FileRecord.summary.ilike(like)))):
            if t in f.path.lower():
                bump(f.path, 8, f"path matches '{t}'", token=t, kind="path")
            else:
                bump(f.path, 2, f"summary mentions '{t}'", token=t, kind="summary")
        for s in db.scalars(select(Symbol).where(
                Symbol.repo_id == repo_id, or_(Symbol.name.ilike(like), Symbol.docstring.ilike(like)))):
            if t in s.name.lower():
                bump(s.file_path, 5, f"{s.kind} `{s.name}`", s.line, token=t, kind="symbol")
            else:
                bump(s.file_path, 2, f"docstring of `{s.name}` mentions '{t}'", s.line, token=t, kind="doc")

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [SourceRef(path=p, score=round(sc, 1), reason="; ".join(reasons[p][:3]), line=first_line.get(p))
            for p, sc in ranked]


def answer_question(db, repo_id: int, question: str) -> tuple[str, list[SourceRef], str | None]:
    sources = search_repo(db, repo_id, question)
    if not sources:
        return ("I couldn't find anything in the index matching that question. "
                "Try different keywords (e.g. a feature name, class name or file name)."), [], None

    if ai_client.enabled:
        contexts = []
        for s in sources[:5]:
            f = db.scalar(select(FileRecord).where(FileRecord.repo_id == repo_id, FileRecord.path == s.path))
            syms = db.scalars(select(Symbol).where(Symbol.repo_id == repo_id, Symbol.file_path == s.path)
                              .limit(15)).all()
            contexts.append({"path": s.path, "summary": f.summary if f else None, "reason": s.reason,
                             "symbols": [x.signature or x.name for x in syms]})
        res = ai_client.answer_question(question, contexts)
        if res:
            return res[0], sources, res[1]

    lines = [f"Based on the code index, these are the most relevant places for “{question}”:"]
    for i, s in enumerate(sources[:5], 1):
        loc = f"{s.path}:{s.line}" if s.line else s.path
        lines.append(f"{i}. `{loc}` — {s.reason}")
    lines.append("Open `GET /api/v1/repos/{id}/files/<path>` for a full explanation of any of these files.")
    return "\n".join(lines), sources, None
