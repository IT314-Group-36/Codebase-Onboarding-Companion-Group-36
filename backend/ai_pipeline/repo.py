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
import time
from pathlib import Path

import httpx

from .clone_limits import CloneLimitError, CloneLimits, run_git
from .config import MAX_FILES, SENSITIVE_PATTERNS, SKIP_DIRS

_GITHUB_URL = re.compile(r"^https://github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$")
_BRANCH = re.compile(r"^[\w][\w./\-]{0,99}$")

# Git (and the parsers/hooks it may start) must not see the server's secrets (SESSION_SECRET, TOKEN_ENCRYPTION_KEY,
# API keys, DATABASE_URL, ...). The child process gets only these variables, from an allow-list.
_GIT_ENV_KEEP = (
    "PATH", "LANG", "LC_ALL", "PYTHONPATH",                                  # PYTHONPATH: the clone worker imports ai_pipeline
    "SSL_CERT_FILE", "SSL_CERT_DIR", "GIT_SSL_CAINFO",                       # CA bundles, if configured
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",                    # proxies, only if configured
    "http_proxy", "https_proxy", "no_proxy", "all_proxy",
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR",   # needed to run programs on Windows / find temp
)
GITHUB_HEADER_KEY = "http.https://github.com/.extraheader"                   # scoped: never sent to any other host


def git_environment(home, token: str | None = None) -> dict:
    """Environment for the Git child process: allow-listed variables, a HOME inside the job directory, no user or
    system Git config, and (private repos) the token header scoped to github.com only."""
    env = {name: os.environ[name] for name in _GIT_ENV_KEEP if name in os.environ}
    env.update(HOME=str(home), USERPROFILE=str(home), GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1",
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    if token:                               # private repos: header via env, never in argv or .git/config
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0=GITHUB_HEADER_KEY,
                   GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}")
    return env


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


def _check_github_size(url: str, token: str | None, limits: CloneLimits, *, timeout: float = 10) -> None:
    """Cheap early rejection. GitHub's history-inclusive KiB size is only a hint.

    Missing/private repos, rate limits and metadata outages still go through the
    bounded Git path, so preflight is never the sole resource protection.
    """
    match = _GITHUB_URL.fullmatch(url)
    if not match:
        return  # local test/demo repositories
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "onboarding-companion"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = httpx.get(
            f"https://api.github.com/repos/{match[1]}/{match[2]}",
            headers=headers, timeout=timeout, follow_redirects=False,
        )
        if response.status_code != 200:
            return
        size = response.json().get("size")
    except (httpx.HTTPError, ValueError, AttributeError):
        return
    if isinstance(size, int) and size * 1024 > limits.max_disk_bytes:
        raise CloneLimitError("Repository is too large for this server's clone disk budget (GitHub size estimate).")


def _check_checkout(tree: bytes, limits: CloneLimits) -> None:
    """Inspect expanded blob sizes before checkout, including compressed large files."""
    total, count = 0, 0
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        count += 1
        if count > MAX_FILES:
            raise CloneLimitError("Repository resource limit exceeded: too many files to check out.")
        metadata = entry.split(b"\t", 1)[0].split()
        if len(metadata) != 4:
            raise RuntimeError("Could not inspect the repository file sizes.")
        if metadata[1] != b"blob":  # submodule commits are never cloned recursively
            continue
        size = int(metadata[3])
        if size > limits.max_file_bytes:
            raise CloneLimitError("Repository resource limit exceeded: a file is too large to check out.")
        total += size
        if total > limits.max_checkout_bytes:
            raise CloneLimitError("Repository resource limit exceeded: expanded checkout is too large.")


def clone_repo(url: str, branch: str, dest, token: str | None = None, timeout: int = 300,
               *, limits: CloneLimits | None = None) -> str:
    """Bounded shallow clone, size inspection, then checkout. Return the commit SHA."""
    limits = limits or CloneLimits()
    deadline = time.monotonic() + timeout
    dest = Path(dest)
    safe_rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _check_github_size(url, token, limits, timeout=min(10, max(0.1, timeout)))
    git = ["git", "-c", "core.symlinks=false", "-c", "core.hooksPath=/dev/null",
           "-c", "pack.threads=1", "-c", "fetch.unpackLimit=1"]
    cmd = [*git, "clone", "--depth", "1", "--single-branch", "--no-tags", "--no-checkout", "--no-local"]
    if branch:
        cmd += ["--branch", validate_branch(branch)]
    cmd += ["--", url, str(dest)]           # "--" stops a URL from being parsed as an option
    env = git_environment(dest.parent, token)       # dest.parent is this job's own directory, removed after the job
    try:
        run_git(cmd, dest, env, deadline, limits)
        tree = run_git([*git, "-C", str(dest), "ls-tree", "-r", "-l", "-z", "HEAD"],
                       dest, env, deadline, limits)
        _check_checkout(tree, limits)
        run_git([*git, "-C", str(dest), "checkout", "--force", "--detach", "HEAD"],
                dest, env, deadline, limits)
        sha = run_git([*git, "-C", str(dest), "rev-parse", "HEAD"], dest, env, deadline, limits)
        return sha.decode("ascii").strip()
    except BaseException as exc:
        # Reap subprocesses (run_git's finally) before deleting partial downloads.
        safe_rmtree(dest)
        if token and isinstance(exc, RuntimeError):
            basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            message = str(exc).replace(token, "***").replace(basic, "***")
            raise type(exc)(message) from None
        raise


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
