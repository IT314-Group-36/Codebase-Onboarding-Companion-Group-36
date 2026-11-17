"""Bounded, redacted README input shared by the module map and repository summary."""
import os
import stat
from pathlib import Path

from .repo import is_sensitive
from .secrets import redact_secrets

MAX_README_BYTES = 200_000
README_SUFFIXES = {"", ".md", ".markdown", ".rst", ".txt"}


def read_readme(root, files: list[str], limit: int = 2000) -> str:
    """Read a regular root-level README, never a sensitive file or a symlink.

    Redact the entire bounded file BEFORE truncating the prompt, so a secret that
    crosses the prompt boundary cannot leak as an unrecognisable partial token.
    Oversized/binary/unreadable candidates are skipped rather than read in full.
    """
    if limit <= 0:
        return ""
    root = Path(root)
    for name in sorted(files):
        if ("/" in name or "\\" in name or not name.lower().startswith("readme")
                or is_sensitive(name) or Path(name).suffix.lower() not in README_SUFFIXES):
            continue
        path = root / name
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                continue
            # O_NOFOLLOW closes the check/open race on the production Linux host.
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            fd = os.open(path, flags | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_README_BYTES:
                    continue
                raw = stream.read(MAX_README_BYTES + 1)
            if len(raw) > MAX_README_BYTES or b"\x00" in raw:
                continue
            text, _ = redact_secrets(raw.decode("utf-8", errors="replace"))
            return text[:limit]
        except OSError:
            continue
    return "(no README found)"
