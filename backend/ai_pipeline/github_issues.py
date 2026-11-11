"""Fetch open issues from the GitHub REST API (blocking, stdlib only; callers run it in a thread).

Design notes
- One request series per label, filtered by GitHub itself, so a repo with thousands of issues is still cheap.
- The issues endpoint also returns pull requests: those are dropped here.
- The token goes into the Authorization header only. It is never logged, stored, or put in an error message.
- Every failure becomes a GitHubError with a message a new developer can act on.
"""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlencode

from .secrets import redact_secrets

DEFAULT_API = "https://api.github.com"
PER_PAGE = 100
MAX_TITLE = 300
MAX_BODY = 6000          # enough for ranking and search; the clone is not kept, and neither are huge issue threads

_CANONICAL_URL = re.compile(r"^https://github\.com/([\w.\-]+)/([\w.\-]+)$")     # form stored by validate_repo_url


class GitHubError(RuntimeError):
    """The issues could not be fetched. The message is safe to show to the user."""


class IssuesDisabled(GitHubError):
    """The repository has the Issues tab turned off (HTTP 410)."""


def parse_owner_repo(url: str) -> tuple[str, str] | None:
    """('owner', 'repo') for a canonical https://github.com/<owner>/<repo> URL, else None (e.g. a local test path)."""
    m = _CANONICAL_URL.match((url or "").strip())
    return (m.group(1), m.group(2)) if m else None


def _api_message(body: bytes, token: str | None) -> str:
    try:
        msg = str(json.loads(body.decode("utf-8", errors="replace")).get("message", ""))
    except (ValueError, AttributeError):
        msg = ""
    if token:
        msg = msg.replace(token, "***")
    return msg[:200]


def _translate(err: urllib.error.HTTPError, token: str | None) -> GitHubError:
    code = err.code
    detail = _api_message(err.read() if err.fp else b"", token)
    if code == 410:
        return IssuesDisabled("Issues are turned off for this repository, so there is nothing to fetch.")
    if code == 401:
        return GitHubError("GitHub rejected the access token (401). Check that it is valid and has not expired.")
    if code == 404:
        return GitHubError("Repository not found on GitHub. If it is private, pass an access_token that can read it.")
    limited = code == 429 or (code == 403 and (err.headers.get("X-RateLimit-Remaining") == "0" or "rate limit" in detail.lower()))
    if limited:
        reset = err.headers.get("X-RateLimit-Reset", "")
        when = ""
        if reset.isdigit():
            when = f" It resets at {datetime.fromtimestamp(int(reset), timezone.utc):%H:%M} UTC."
        return GitHubError("GitHub API rate limit reached." + when +
                           " Pass an access_token (or set GITHUB_TOKEN on the server) for a much higher limit.")
    if code == 403:
        return GitHubError(f"GitHub refused access (403). {detail}".strip())
    return GitHubError(f"GitHub returned HTTP {code}. {detail}".strip())


def _get_json(url: str, token: str | None, timeout: int):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "onboarding-companion"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:                       # must come before URLError (it is a subclass)
        raise _translate(e, token) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GitHubError(f"Could not reach GitHub ({getattr(e, 'reason', e)}).") from None
    except ValueError:
        raise GitHubError("GitHub sent a response that could not be read.") from None


def fetch_issues(owner: str, repo: str, token: str | None, labels: list[str], *, api_url: str = DEFAULT_API,
                 max_pages: int = 3, timeout: int = 15) -> list[dict]:
    """Open issues (no pull requests) that carry at least one of `labels`, de-duplicated by issue number."""
    found: dict[int, dict] = {}
    for label in labels:
        for page in range(1, max_pages + 1):
            query = urlencode({"state": "open", "labels": label, "per_page": PER_PAGE, "page": page,
                               "sort": "updated", "direction": "desc"})
            batch = _get_json(f"{api_url.rstrip('/')}/repos/{owner}/{repo}/issues?{query}", token, timeout)
            if not isinstance(batch, list):
                raise GitHubError("GitHub sent an unexpected response for the issue list.")
            for item in batch:
                if isinstance(item, dict) and "pull_request" not in item and isinstance(item.get("number"), int):
                    found.setdefault(item["number"], item)
            if len(batch) < PER_PAGE:
                break
    return list(found.values())


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_issue(raw: dict) -> dict:
    """GitHub JSON -> the columns we store. Secrets pasted into an issue are redacted before they reach the DB."""
    labels = [(lab.get("name") if isinstance(lab, dict) else str(lab)) for lab in raw.get("labels") or []]
    assignees = len(raw.get("assignees") or []) or (1 if raw.get("assignee") else 0)
    body, _ = redact_secrets((raw.get("body") or "")[:MAX_BODY])
    return {
        "number": int(raw["number"]),
        "title": (raw.get("title") or "").strip()[:MAX_TITLE],
        "body": body,
        "labels": [x for x in labels if x],
        "url": raw.get("html_url") or "",
        "comments": int(raw.get("comments") or 0),
        "assignees": assignees,
        "locked": bool(raw.get("locked")),
        "gh_created_at": _parse_time(raw.get("created_at")),
        "gh_updated_at": _parse_time(raw.get("updated_at")),
    }
