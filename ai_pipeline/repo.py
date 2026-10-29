"""Helpers to clone a repo and list files. In the real system Backend does S1-4/S1-5;
this module lets the AI team run and test on its own."""
import fnmatch
import os
import json
import shutil
import stat
import subprocess
from pathlib import Path

from .config import SENSITIVE_PATTERNS, SKIP_DIRS


def safe_rmtree(path) -> None:
    """rmtree that also works on Windows, where .git files are read-only."""
    def _onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_onerror) if Path(path).exists() else None


def is_sensitive(name: str) -> bool:
    return any(fnmatch.fnmatch(name.lower(), p) for p in SENSITIVE_PATTERNS)


def clone_repo(url: str, branch: str, dest: Path) -> None:
    """Shallow clone (FR-01). Raises RuntimeError with a readable message on failure."""
    dest = Path(dest)
    safe_rmtree(dest)
    cmd = ["git", "clone", "--depth", "1", "--single-branch"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [url, str(dest)]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)
    if r.returncode != 0:
        raise RuntimeError("Could not clone the repo. Is it public, and are the URL/branch correct?\n" + r.stderr)


def scan_files(root) -> tuple[list[str], list[str]]:
    """Returns (all_files, safe_files). Sensitive files stay in all_files so they show as
    map nodes, but are never in safe_files, so their content is never embedded."""
    root = Path(root)
    all_files, safe_files = [], []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            rel = (Path(dirpath) / n).relative_to(root).as_posix()
            all_files.append(rel)
            if not is_sensitive(n):
                safe_files.append(rel)
    return sorted(all_files), sorted(safe_files)


def cleanup(path) -> None:
    """DR-03: delete the temporary clone after analysis."""
    safe_rmtree(path)


def save_file_tree(root, all_files: list[str], safe_files: list[str], out_dir) -> dict:
    """Stores the folder/file structure of the repo as JSON + a readable tree.txt.
    This is what stays after the clone is deleted (DR-03)."""
    root, out_dir = Path(root), Path(out_dir)
    safe = set(safe_files)
    entries = []
    for rel in all_files:
        try:
            size = (root / rel).stat().st_size
        except OSError:
            size = 0
        entries.append({"path": rel, "size": size, "extension": Path(rel).suffix.lower(),
                        "sensitive": rel not in safe})
    folders = sorted({"/".join(f.split("/")[:i]) for f in all_files for i in range(1, len(f.split("/")))})
    (out_dir / "file_tree.json").write_text(json.dumps({"folders": folders, "files": entries}, indent=2))
    (out_dir / "tree.txt").write_text("\n".join(all_files))
    return {"files": len(entries), "folders": len(folders)}
