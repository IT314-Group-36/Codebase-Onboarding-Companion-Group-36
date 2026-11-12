"""On-demand repository Git history, fetched from GitHub and never persisted."""
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_github_client, get_ready_user_repo
from app.models import Repository, User
from app.services.github import GitHubClient, GitHubError, user_github_token

router = APIRouter(prefix="/repos", tags=["history"])


@router.get("/{repo_id}/history")
async def repository_history(
    path: str | None = Query(None, max_length=500),
    limit: int = Query(50, ge=1, le=100),
    repo: Repository = Depends(get_ready_user_repo),
    user: User = Depends(get_current_user),
    github: GitHubClient = Depends(get_github_client),
):
    """Return recent commits and a contribution count from that bounded sample."""
    parsed = urlparse(repo.url)
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if parsed.hostname != "github.com" or len(parts) != 2:
        raise HTTPException(422, "Git history is available for GitHub repositories only.")
    full_name = "/".join(parts)
    try:
        raw_commits = await github.list_commits(
            user_github_token(user), full_name, branch=repo.branch or None, path=path, per_page=limit
        )
    except GitHubError as e:
        status = {"reauth": 403, "not_found": 404, "rate_limit": 429}.get(e.kind, 502)
        raise HTTPException(status, str(e)) from e

    commits = []
    contributors: dict[str, dict] = {}
    for item in raw_commits:
        gh_author = item.get("author") or {}
        commit = item.get("commit") or {}
        author_info = commit.get("author") or {}
        login = gh_author.get("login")
        name = author_info.get("name") or "Unknown author"
        key = login or name
        commits.append({
            "sha": item.get("sha", ""),
            "short_sha": (item.get("sha") or "")[:7],
            "message": (commit.get("message") or "(no commit message)").splitlines()[0][:240],
            "date": author_info.get("date") or (commit.get("committer") or {}).get("date"),
            "author": {"login": login, "name": name, "avatar_url": gh_author.get("avatar_url")},
            "url": item.get("html_url", ""),
        })
        contributor = contributors.setdefault(key, {
            "login": login, "name": name, "avatar_url": gh_author.get("avatar_url"), "commits": 0,
        })
        contributor["commits"] += 1

    total = len(commits)
    ranked = sorted(contributors.values(), key=lambda x: (-x["commits"], x["name"].lower()))
    for contributor in ranked:
        contributor["share"] = round(contributor["commits"] / total * 100, 1) if total else 0
    return {"repository": full_name, "branch": repo.branch or None, "path": path,
            "sample_size": total, "commits": commits, "contributors": ranked}
