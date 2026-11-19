"""Read-only, bounded check of a deployed backend revision. No production credentials needed."""
import argparse
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def verify(url, revision, *, timeout=600, interval=10):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("Use an HTTPS backend origin, without credentials, path, query or fragment")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected revision must be a full lowercase 40-character commit SHA")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(url.rstrip("/") + "/ready", headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=min(10, max(0.1, deadline - time.monotonic()))) as response:
                body = json.loads(response.read(4096))
                if (response.status == 200 and isinstance(body, dict)
                        and body.get("status") == "ready" and body.get("revision") == revision):
                    print(f"Backend is database-ready at revision {revision}")
                    return
        except (OSError, ValueError):
            pass  # Do not print upstream response bodies or potentially sensitive network errors.
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval, remaining))
    raise TimeoutError("Backend did not become database-ready at the expected revision before the deadline")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    verify(args.url, args.revision)
