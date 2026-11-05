"""Clone and scan helpers.

Fixes vs. the first version: URL/branch validation (no git option injection, https GitHub only),
one directory per job (callers pass `dest`), token passed through git's environment instead of
argv/URL, symlinks never followed, file/size caps, commit SHA returned.
"""
import base64
import fnmatch
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

from .config import MAX_FILES, SENSITIVE_PATTERNS, SKIP_DIRS

_GITHUB_URL = re.compile(r"^https://github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$")
_BRANCH = re.compile(r"^[\w][\w./\-]{0,99}$")


def validate_repo_url(url: str, allow_local: bool = False) -> str:
    """Return a canonical https://github.com/<owner>/<repo> URL or raise ValueError.

    allow_local exists only for tests / local demos: it accepts an existing directory path.
    """
    url = (url or "").strip()
    m = _GITHUB_URL.match(url)
    if m:
        return f"https://github.com/{m.group(1)}/{m.group(2)}"
    if allow_local and Path(url).is_dir():
        return str(Path(url).resolve())
    raise ValueError("Only https://github.com/<owner>/<repo> URLs are supported")


def validate_branch(branch: str) -> str:
    branch = (branch or "").strip()
    if not branch:
        return ""
    if not _BRANCH.match(branch) or ".." in branch or branch.endswith("/"):
        raise ValueError("Invalid branch name")
    return branch


def safe_rmtree(path) -> None:
    """rmtree that also works on Windows, where .git files are read-only."""
    def _onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    if Path(path).exists():
        shutil.rmtree(path, onerror=_onerror)


def cleanup(path) -> None:
    """DR-03: delete the temporary clone after analysis."""
    safe_rmtree(path)


def clone_repo(url: str, branch: str, dest, token: str | None = None, timeout: int = 300) -> str:
    """Shallow clone (FR-01). Returns the commit SHA. Raises RuntimeError with a readable message."""
    dest = Path(dest)
    safe_rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "-c", "core.symlinks=false", "-c", "core.hooksPath=/dev/null",
           "clone", "--depth", "1", "--single-branch", "--no-tags"]
    if branch:
        cmd += ["--branch", validate_branch(branch)]
    cmd += ["--", url, str(dest)]           # "--" stops a URL from being parsed as an option
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token:                               # private repos: header via env, never in argv or .git/config
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraheader",
                   GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        safe_rmtree(dest)
        raise RuntimeError("Cloning timed out. The repository may be too large.") from None
    if r.returncode != 0:
        safe_rmtree(dest)
        raise RuntimeError("Could not clone the repo. Is it public (or is the token valid), and are the "
                           "URL/branch correct?\n" + r.stderr.replace(token or "\0", "***")[-500:])
    sha = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True)
    return sha.stdout.strip()


def is_sensitive(name: str) -> bool:
    return any(fnmatch.fnmatch(name.lower(), p) for p in SENSITIVE_PATTERNS)


def scan_files(root) -> tuple[list[str], list[str]]:
    """Returns (all_files, safe_files). Sensitive files stay in all_files so they show as map
    nodes, but are never in safe_files, so their content is never read. Symlinks are skipped."""
    root = Path(root)
    all_files, safe_files = [], []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not os.path.islink(os.path.join(dirpath, d))]
        for n in names:
            full = os.path.join(dirpath, n)
            if os.path.islink(full):
                continue
            rel = Path(full).relative_to(root).as_posix()
            all_files.append(rel)
            if not is_sensitive(n):
                safe_files.append(rel)
            if len(all_files) >= MAX_FILES:
                return sorted(all_files), sorted(safe_files)
    return sorted(all_files), sorted(safe_files)
