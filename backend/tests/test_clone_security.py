"""Resource checks must run during download and before expanding a checkout."""
import base64
import os
import subprocess
import sys
import time
from dataclasses import replace

import httpx
import pytest

from ai_pipeline import repo
from ai_pipeline.clone_limits import CloneLimitError, CloneLimits, run_git
from app.core.config import Settings
from app.services import indexing


@pytest.mark.parametrize("size", [2048, 2049])
def test_github_preflight_rejects_large_repo_before_git(monkeypatch, tmp_path, size):
    def get(url, **kwargs):
        assert url == "https://api.github.com/repos/owner/repo"
        assert kwargs["headers"]["Authorization"] == "Bearer private-token"
        assert kwargs["follow_redirects"] is False
        return httpx.Response(200, json={"size": size})

    monkeypatch.setattr(repo.httpx, "get", get)
    monkeypatch.setattr(repo, "run_git", lambda *a: pytest.fail("Git must not start"))
    with pytest.raises(CloneLimitError, match="GitHub size estimate"):
        repo.clone_repo("https://github.com/owner/repo", "", tmp_path / "clone", "private-token",
                        limits=CloneLimits(max_disk_bytes=1024))


@pytest.mark.parametrize("status", [301, 401, 403, 404, 500])
def test_unavailable_metadata_does_not_replace_runtime_limits(monkeypatch, status):
    monkeypatch.setattr(repo.httpx, "get", lambda *a, **k: httpx.Response(status))
    repo._check_github_size("https://github.com/owner/repo", None, CloneLimits())


def test_metadata_network_failure_is_best_effort(monkeypatch):
    def get(*args, **kwargs):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(repo.httpx, "get", get)
    repo._check_github_size("https://github.com/owner/repo", None, CloneLimits())


def tree_entry(size, name=b"file.txt"):
    return b"100644 blob " + b"a" * 40 + b" " + str(size).encode() + b"\t" + name + b"\0"


def test_expanded_size_and_individual_file_limits():
    limits = CloneLimits(max_file_bytes=100, max_checkout_bytes=150)
    repo._check_checkout(tree_entry(75) + tree_entry(75, b"b.txt"), limits)
    with pytest.raises(CloneLimitError, match="expanded checkout"):
        repo._check_checkout(tree_entry(76) + tree_entry(75, b"b.txt"), limits)
    with pytest.raises(CloneLimitError, match="a file is too large"):
        repo._check_checkout(tree_entry(101), limits)


def test_file_count_limit_and_unusual_filenames(monkeypatch):
    monkeypatch.setattr(repo, "MAX_FILES", 1)
    repo._check_checkout(tree_entry(1, b"file\nwith\ttabs"), CloneLimits())
    with pytest.raises(CloneLimitError, match="too many files"):
        repo._check_checkout(tree_entry(1) * 2, CloneLimits())


def test_checks_sizes_before_checkout_and_cleans_up(monkeypatch, tmp_path):
    calls = []
    dest = tmp_path / "clone"

    def git(cmd, root, env, deadline, limits):
        calls.append(cmd)
        if "clone" in cmd:
            root.mkdir()
            (root / "partial").write_text("download")
        if "ls-tree" in cmd:
            return tree_entry(101)
        return b""

    monkeypatch.setattr(repo, "run_git", git)
    with pytest.raises(CloneLimitError):
        repo.clone_repo("local-test", "", dest, limits=CloneLimits(max_file_bytes=100))
    assert "--no-checkout" in calls[0] and "--no-local" in calls[0]
    assert not any("checkout" in cmd for cmd in calls)
    assert not dest.exists()


def test_real_local_clone_and_compressed_oversize_rejection(git_repo, tmp_path):
    dest = tmp_path / "clone"
    sha = repo.clone_repo(str(git_repo), "", dest)
    assert len(sha) == 40 and (dest / "README.md").is_file()
    with pytest.raises(CloneLimitError, match="a file is too large"):
        repo.clone_repo(str(git_repo), "", dest, limits=CloneLimits(max_file_bytes=10))
    assert not dest.exists()


def test_error_never_contains_raw_or_encoded_token(monkeypatch, tmp_path):
    token = "private-access-token"
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()

    def fail(*args):
        raise RuntimeError(f"Could not clone {token} {encoded}")
    monkeypatch.setattr(repo, "run_git", fail)
    with pytest.raises(RuntimeError) as error:
        repo.clone_repo("local-test", "", tmp_path / "clone", token)
    assert token not in str(error.value) and encoded not in str(error.value)


async def test_limit_rejection_is_not_retried_with_saved_token(monkeypatch, tmp_path):
    monkeypatch.setattr(indexing, "get_settings", lambda: Settings(_env_file=None))
    calls = []

    def clone(*args, **kwargs):
        calls.append((args, kwargs))
        raise CloneLimitError("too large")

    async def saved(*args):
        pytest.fail("Do not load credentials after a size rejection")

    monkeypatch.setattr(indexing, "clone_repo", clone)
    monkeypatch.setattr(indexing, "_saved_token", saved)
    with pytest.raises(CloneLimitError):
        await indexing._clone(1, "local-test", "", tmp_path, None)
    assert len(calls) == 1 and isinstance(calls[0][1]["limits"], CloneLimits)


def test_watchdog_times_out_and_reaps_process_tree(tmp_path):
    root = tmp_path / "clone"
    root.mkdir()
    limits = replace(CloneLimits(), min_free_disk_bytes=0)
    with pytest.raises(CloneLimitError, match="timed out"):
        run_git([sys.executable, "-c", "import time; time.sleep(30)"], root, dict(os.environ),
                time.monotonic() + 0.5, limits)


def test_watchdog_rejects_disk_usage(tmp_path):
    root = tmp_path / "clone"
    root.mkdir()
    (root / "oversized").write_bytes(b"x" * 2000)
    limits = replace(CloneLimits(), max_disk_bytes=1000, min_free_disk_bytes=0)
    with pytest.raises(CloneLimitError, match="disk budget"):
        run_git([sys.executable, "-c", "import time; time.sleep(30)"], root, dict(os.environ),
                time.monotonic() + 5, limits)


def test_watchdog_rejects_disk_growth_during_download(tmp_path):
    root = tmp_path / "clone"
    root.mkdir()
    limits = replace(CloneLimits(), max_disk_bytes=1024 * 1024, min_free_disk_bytes=0)
    code = (
        "from pathlib import Path; import time; "
        f"p = Path({str(root / 'download.pack')!r}); "
        "p.write_bytes(b'x' * 2097152); time.sleep(30)"
    )
    with pytest.raises(CloneLimitError):
        run_git([sys.executable, "-c", code], root, dict(os.environ),
                time.monotonic() + 5, limits)


def test_watchdog_bounds_subprocess_output(tmp_path):
    root = tmp_path / "clone"
    root.mkdir()
    limits = replace(CloneLimits(), min_free_disk_bytes=0)
    with pytest.raises(CloneLimitError, match="output is too large"):
        run_git([sys.executable, "-c", "print('x' * (9 * 1024 * 1024))"], root, dict(os.environ),
                time.monotonic() + 10, limits)


def test_watchdog_reserves_free_disk_space(tmp_path):
    root = tmp_path / "clone"
    root.mkdir()
    limits = replace(CloneLimits(), min_free_disk_bytes=10**20)
    with pytest.raises(CloneLimitError, match="free disk space"):
        run_git([sys.executable, "-c", "import time; time.sleep(30)"], root, dict(os.environ),
                time.monotonic() + 5, limits)


@pytest.mark.skipif(sys.platform != "linux", reason="Kernel resource limits run on production Linux")
def test_linux_worker_enforces_kernel_limits():
    code = (
        "import resource; "
        "assert resource.getrlimit(resource.RLIMIT_AS) == (134217728, 134217728); "
        "assert resource.getrlimit(resource.RLIMIT_FSIZE) == (1048576, 1048576); "
        "assert resource.getrlimit(resource.RLIMIT_CPU) == (2, 2); "
        "assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)"
    )
    subprocess.run([
        sys.executable, "-m", "ai_pipeline.clone_worker", "134217728", "1048576", "2",
        sys.executable, "-c", code,
    ], check=True, timeout=10)


@pytest.mark.skipif(sys.platform != "linux", reason="Kernel resource limits run on production Linux")
@pytest.mark.parametrize("kind", ["memory", "file", "cpu"])
def test_linux_worker_actually_rejects_excessive_resources(tmp_path, kind):
    target = tmp_path / "oversized"
    code = {
        "memory": "bytearray(512 * 1024 * 1024)",
        "file": f"with open({str(target)!r}, 'wb') as stream:\n    stream.write(b'x' * 2048)",
        "cpu": "while True: pass",
    }[kind]
    result = subprocess.run([
        sys.executable, "-m", "ai_pipeline.clone_worker", "134217728", "1024", "1",
        sys.executable, "-c", code,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    assert result.returncode != 0
    if kind == "file":
        assert target.stat().st_size <= 1024
