"""Resource guardrails for Git download, inspection and checkout."""
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import disk_usage

MIB = 1024 * 1024


class CloneLimitError(RuntimeError):
    """A resource rejection must not be retried with a different credential."""


@dataclass(frozen=True)
class CloneLimits:
    max_disk_bytes: int = 200 * MIB
    max_checkout_bytes: int = 100 * MIB
    max_file_bytes: int = 20 * MIB
    memory_bytes: int = 256 * MIB
    cpu_seconds: int = 120
    min_free_disk_bytes: int = 256 * MIB


def directory_bytes(root: Path, budget: int) -> int:
    """Stop counting as soon as the budget is exceeded; never follow symlinks."""
    total = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(parent) / d).is_symlink()]
        for name in files:
            try:
                total += (Path(parent) / name).lstat().st_size
            except FileNotFoundError:  # Git renames/deletes temporary files while running.
                continue
            if total > budget:
                return total
    return total


def stop_process_tree(process: subprocess.Popen) -> None:
    """Reap Git AND its transport/index-pack descendants before removing files."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        # CREATE_NEW_PROCESS_GROUP alone does not make kill() terminate children.
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    process.wait()


def run_git(cmd: list[str], root: Path, env: dict, deadline: float, limits: CloneLimits) -> bytes:
    """Run Git with bounded output, wall time and aggregate disk monitoring.

    Linux additionally enforces per-process address space/CPU and per-file size.
    Aggregate disk monitoring can overshoot between checks; use a quota-limited
    work filesystem if a strict aggregate storage boundary is required.
    """
    wrapped = [
        sys.executable, "-m", "ai_pipeline.clone_worker",
        str(limits.memory_bytes), str(limits.max_disk_bytes), str(limits.cpu_seconds), *cmd,
    ] if sys.platform == "linux" else cmd
    options = {"start_new_session": True} if os.name == "posix" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
    }
    if disk_usage(root.parent).free < limits.min_free_disk_bytes:
        raise CloneLimitError("Repository resource limit exceeded: insufficient free disk space.")
    # Files, not PIPE/communicate: a noisy subprocess cannot fill API memory.
    with tempfile.TemporaryFile(dir=root.parent) as out, tempfile.TemporaryFile(dir=root.parent) as err:
        process = subprocess.Popen(wrapped, stdout=out, stderr=err, env=env, **options)
        try:
            while True:
                output_bytes = os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size
                if output_bytes > 8 * MIB:
                    raise CloneLimitError("Repository resource limit exceeded: Git output is too large.")
                if directory_bytes(root, limits.max_disk_bytes) + output_bytes > limits.max_disk_bytes:
                    raise CloneLimitError("Repository resource limit exceeded: clone disk budget reached.")
                if disk_usage(root.parent).free < limits.min_free_disk_bytes:
                    raise CloneLimitError("Repository resource limit exceeded: insufficient free disk space.")
                if time.monotonic() >= deadline:
                    raise CloneLimitError("Cloning timed out. The repository may be too large.")
                if process.poll() is not None:
                    break  # The checks above also run once after the process finishes.
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                err.seek(0)
                detail = err.read(2000).decode("utf-8", errors="replace")
                if process.returncode < 0 or any(word in detail.lower() for word in (
                    "cannot allocate memory", "out of memory", "file too large", "died of signal",
                )):
                    raise CloneLimitError("Repository resource limit exceeded: Git exceeded its "
                                          "memory, CPU or file-size allowance.")
                raise RuntimeError("Could not clone the repo. Check its URL, branch and GitHub access. "
                                   "Git may also have exceeded its memory, CPU or file-size limit.\n" + detail)
            out.seek(0)
            return out.read(8 * MIB + 1)
        finally:
            stop_process_tree(process)
