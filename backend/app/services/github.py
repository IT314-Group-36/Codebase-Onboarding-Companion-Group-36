"""Minimal GitHub client: OAuth code exchange, the signed-in user, their repositories and a repo's branches.

Every GitHub failure becomes a GitHubError whose `kind` the API turns into a clear HTTP answer:
  reauth      the saved token was revoked/expired (or missing) -> ask the user to sign in again
  not_found   no such repo, or this account cannot see it
  rate_limit  GitHub's API limit was hit
  error       anything else (network, 5xx)
Tokens are only ever sent in the Authorization header and are never logged or put in messages.
"""
import base64
import binascii
from urllib.parse import quote, urlencode

import httpx

from app.core.config import get_settings
from app.core.security import SecurityConfigError, TokenDecryptError, decrypt_token
from app.models import User

API = "https://api.github.com"
OAUTH = "https://github.com/login/oauth"
# `repo` is the smallest OAuth scope that lets us clone private repos (GitHub has no read-only variant; a GitHub App
# would, but needs a per-repo install flow). We only ever read with it.
SCOPES = "repo read:user"


class GitHubError(Exception):
    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind


def user_github_token(user: User) -> str:
    """The user's saved GitHub token, decrypted. Raises GitHubError(kind="reauth") when it is missing or unreadable."""
    if not user.encrypted_access_token:
        raise GitHubError("No GitHub sign-in is saved for this account. Sign in with GitHub.", "reauth")
    try:
        return decrypt_token(user.encrypted_access_token)
    except (TokenDecryptError, SecurityConfigError) as e:
        raise GitHubError("Your saved GitHub sign-in can no longer be used. Sign in with GitHub again.", "reauth") from e


def _raise_for_status(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code == 401:
        raise GitHubError("GitHub rejected the saved sign-in. Sign in with GitHub again.", "reauth")
    if r.status_code in (403, 429) and (r.headers.get("x-ratelimit-remaining") == "0" or "rate limit" in r.text.lower()):
        raise GitHubError("GitHub rate limit reached. Try again in a few minutes.", "rate_limit")
    if r.status_code == 404:
        raise GitHubError("Not found, or your GitHub account cannot access it.", "not_found")
    if r.status_code == 409 and "empty" in r.text.lower():
        raise GitHubError("This repository has no commits yet.", "empty")
    raise GitHubError(f"GitHub returned an error ({r.status_code}). Try again later.")


class GitHubClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 15.0):
        self._transport, self._timeout = transport, timeout          # `transport` lets tests fake github.com

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=self._timeout, headers={
            "User-Agent": "codebase-onboarding-companion", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"})

    # ---- OAuth ----
    @staticmethod
    def authorize_url(state: str) -> str:
        cfg = get_settings()
        return f"{OAUTH}/authorize?" + urlencode({
            "client_id": cfg.github_client_id, "redirect_uri": cfg.github_redirect_uri, "scope": SCOPES, "state": state})

    async def exchange_code(self, code: str) -> tuple[str, str]:
        """Trade the one-time `code` for (access_token, granted_scopes)."""
        cfg = get_settings()
        try:
            async with self._http() as c:
                r = await c.post(f"{OAUTH}/access_token", headers={"Accept": "application/json"}, json={
                    "client_id": cfg.github_client_id, "client_secret": cfg.github_client_secret,
                    "code": code, "redirect_uri": cfg.github_redirect_uri})
        except httpx.HTTPError as e:
            raise GitHubError("Could not reach GitHub. Try again in a moment.") from e
        if r.status_code != 200:
            raise GitHubError(f"GitHub returned an error ({r.status_code}) while signing in.")
        data = r.json()
        if not data.get("access_token"):                        # GitHub answers 200 with {"error": ...} for a bad/used code
            raise GitHubError("GitHub did not accept the sign-in code. Please try signing in again.")
        return data["access_token"], data.get("scope", "")

    # ---- API ----
    async def _get(self, path: str, token: str | None, params: dict | None = None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            async with self._http() as c:
                r = await c.get(f"{API}{path}", params=params, headers=headers)
        except httpx.HTTPError as e:
            raise GitHubError("Could not reach GitHub. Try again in a moment.") from e
        _raise_for_status(r)
        return r

    async def get_file_content(self, full_name: str, path: str, ref: str, token: str | None) -> str:
        """Fetch one file at an immutable commit SHA via the GitHub Contents API.

        The caller must first verify that `path` belongs to the indexed repository and is not sensitive.
        GitHub's Contents API supports files up to 1 MB; larger files are rejected explicitly.
        """
        if not ref or not full_name or not path:
            raise GitHubError("Repository, file path and indexed commit are required.")
        safe_path = quote(path, safe="/")
        r = await self._get(f"/repos/{full_name}/contents/{safe_path}", token, {"ref": ref})
        try:
            data = r.json()
        except ValueError as e:
            raise GitHubError("GitHub returned an unreadable file response.") from e
        if data.get("type") != "file":
            raise GitHubError("The requested GitHub path is not a regular file.", "not_found")
        if int(data.get("size") or 0) > 1_000_000:
            raise GitHubError("This file exceeds GitHub's 1 MB Contents API limit.")
        if data.get("encoding") != "base64" or "content" not in data:
            raise GitHubError("GitHub did not return file contents (the file may be too large).")
        try:
            raw = base64.b64decode(data["content"], validate=False)
            return raw.decode("utf-8", errors="replace")
        except (binascii.Error, ValueError, UnicodeDecodeError) as e:
            raise GitHubError("GitHub returned invalid file content.") from e

    async def get_user(self, token: str) -> dict:
        return (await self._get("/user", token)).json()

    async def list_repos(self, token: str, page: int = 1, per_page: int = 30) -> tuple[list[dict], bool]:
        """One page of repos the user can access (own, collaborator, organization), newest activity first."""
        r = await self._get("/user/repos", token, {
            "sort": "pushed", "per_page": per_page, "page": page,
            "affiliation": "owner,collaborator,organization_member"})
        repos = [{
            "full_name": x["full_name"], "url": x["html_url"], "private": bool(x.get("private")),
            "default_branch": x.get("default_branch"), "description": x.get("description"),
            "language": x.get("language"), "updated_at": x.get("pushed_at") or x.get("updated_at"),
            "owner": (x.get("owner") or {}).get("login", ""),
        } for x in r.json()]
        return repos, "next" in r.links

    async def list_branches(self, token: str, full_name: str) -> tuple[str | None, list[str], bool]:
        """(default_branch, branch names, truncated). Only the first 100 branches are returned."""
        info = (await self._get(f"/repos/{full_name}", token)).json()
        r = await self._get(f"/repos/{full_name}/branches", token, {"per_page": 100})
        return info.get("default_branch"), [b["name"] for b in r.json()], "next" in r.links


    async def list_commits(self, token: str | None, full_name: str, *, branch: str | None = None,
                          path: str | None = None, per_page: int = 50) -> list[dict]:
        """Read a bounded recent commit sample, optionally scoped to a branch and file/folder path."""
        params: dict[str, str | int] = {"per_page": min(max(per_page, 1), 100)}
        if branch:
            params["sha"] = branch
        if path:
            params["path"] = path
        try:
            r = await self._get(f"/repos/{full_name}/commits", token, params)
        except GitHubError as e:
            if e.kind == "empty":
                return []
            raise
        return r.json()
