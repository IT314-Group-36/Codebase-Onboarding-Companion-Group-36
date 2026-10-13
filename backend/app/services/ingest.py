"""Repository ingestion: clone/read -> analyze -> store in DB."""
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete

from ..config import settings
from ..database import SessionLocal
from ..models import FileRecord, ImportEdge, Question, Repository, Symbol
from .analyzer import (LANG_BY_EXT, analyze_file, heuristic_summary, module_for,
                       resolve_import)

SKIP_DIRS = {"node_modules", "venv", "env", "__pycache__", "dist", "build", "target",
             "vendor", "site-packages", "coverage"}


def is_url(source: str) -> bool:
    return source.startswith(("https://", "git@"))


def validate_source(source: str) -> None:
    if is_url(source):
        return
    if not settings.allow_local_paths:
        raise ValueError("Local paths are disabled on this server; provide a git URL.")
    if not Path(source).expanduser().is_dir():
        raise ValueError(f"Path not found or not a directory: {source}")


def derive_name(source: str) -> str:
    tail = source.rstrip("/").split("/")[-1].split(":")[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    if tail in ("", ".", ".."):
        tail = Path(source).expanduser().resolve().name
    return tail or "repository"


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower() or "repo"


def prepare_source(repo: Repository) -> Path:
    if is_url(repo.source):
        dest = Path(settings.repos_dir) / f"{repo.id}-{_slug(repo.name)}"
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "--", repo.source, str(dest)],
                       check=True, capture_output=True, text=True, timeout=settings.clone_timeout)
        return dest.resolve()
    return Path(repo.source).expanduser().resolve()


def iter_source_files(root: Path):
    repos_dir = Path(settings.repos_dir).resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")
                       and not d.endswith(".egg-info") and (dp / d).resolve() != repos_dir]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in LANG_BY_EXT:
                continue
            ap = dp / fn
            try:
                if ap.stat().st_size > settings.max_file_bytes:
                    continue
            except OSError:
                continue
            yield ap, ap.relative_to(root).as_posix()


def read_repo_file(repo: Repository, rel_path: str) -> str | None:
    """Read a file from the repo checkout (guards against path traversal)."""
    if not repo.local_path:
        return None
    root = Path(repo.local_path).resolve()
    p = (root / rel_path).resolve()
    if not p.is_relative_to(root) or not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="ignore")


def purge_repo_data(db, repo_id: int, include_questions: bool = False) -> None:
    for model in (Symbol, ImportEdge, FileRecord):
        db.execute(delete(model).where(model.repo_id == repo_id))
    if include_questions:
        db.execute(delete(Question).where(Question.repo_id == repo_id))


def delete_repo(db, repo: Repository) -> None:
    purge_repo_data(db, repo.id, include_questions=True)
    if is_url(repo.source) and repo.local_path:
        shutil.rmtree(repo.local_path, ignore_errors=True)
    db.delete(repo)
    db.commit()


def index_repository(repo_id: int) -> None:
    """Runs in a background task with its own DB session."""
    db = SessionLocal()
    try:
        repo = db.get(Repository, repo_id)
        if repo is None:
            return
        repo.status, repo.error = "indexing", None
        db.commit()
        try:
            root = prepare_source(repo)
            repo.local_path = str(root)
            purge_repo_data(db, repo_id)

            entries = list(iter_source_files(root))
            path_set = {rel for _, rel in entries}
            n_files = 0
            for abs_path, rel in entries:
                text = abs_path.read_text(encoding="utf-8", errors="ignore")
                a = analyze_file(rel, text)
                db.add(FileRecord(repo_id=repo_id, path=rel, module=module_for(rel), language=a.language,
                                  size_bytes=len(text.encode("utf-8", errors="ignore")),
                                  line_count=a.line_count, summary=heuristic_summary(rel, a)))
                for s in a.symbols:
                    db.add(Symbol(repo_id=repo_id, file_path=rel, name=s.name, kind=s.kind,
                                  line=s.line, signature=s.signature, docstring=s.docstring))
                seen: set[tuple[str, str | None]] = set()
                for module, names in a.imports:
                    targets = resolve_import(rel, a.language, module, names, path_set) or [None]
                    for t in targets:
                        if (module, t) not in seen:
                            seen.add((module, t))
                            db.add(ImportEdge(repo_id=repo_id, source_path=rel, target=module, target_path=t))
                n_files += 1

            repo.file_count = n_files
            repo.status = "ready"
            repo.indexed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            repo = db.get(Repository, repo_id)
            msg = exc.stderr if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
            if isinstance(exc, FileNotFoundError) and "git" in str(exc):
                msg = "git is not installed on the server"
            repo.status, repo.error = "failed", msg[:1000]
            db.commit()
    finally:
        db.close()
