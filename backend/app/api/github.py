"""GitHub data for the connect-repository screen: the signed-in user's repositories and a repo's branches."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_github_client
from app.models import User
from app.schemas import BranchList, GitHubRepoList
from app.services.github import GitHubClient, GitHubError, user_github_token

router = APIRouter(prefix="/github", tags=["github"])


def to_http(e: GitHubError) -> HTTPException:
    if e.kind == "reauth":          # 403, not 401: the app login is fine, only the GitHub token needs refreshing
        return HTTPException(403, {"code": "github_reauth_required", "message": str(e)})
    if e.kind == "not_found":
        return HTTPException(404, str(e))
    if e.kind == "rate_limit":
        return HTTPException(429, str(e))
    return HTTPException(502, str(e))


@router.get("/repos", response_model=GitHubRepoList)
async def my_repos(page: int = Query(1, ge=1, le=100), per_page: int = Query(30, ge=1, le=100), q: str = Query("", max_length=100),
                   user: User = Depends(get_current_user), github: GitHubClient = Depends(get_github_client)):
    """One page of the repositories this user can read on GitHub. `q` filters that page by name or description."""
    try:
        repos, has_more = await github.list_repos(user_github_token(user), page, per_page)
    except GitHubError as e:
        raise to_http(e) from e
    if q.strip():
        needle = q.strip().lower()
        repos = [r for r in repos if needle in r["full_name"].lower() or needle in (r["description"] or "").lower()]
    return {"repos": repos, "page": page, "has_more": has_more}


@router.get("/branches", response_model=BranchList)
async def branches(repo: str = Query(..., pattern=r"^[\w.\-]+/[\w.\-]+$", description="owner/name"),
                   user: User = Depends(get_current_user), github: GitHubClient = Depends(get_github_client)):
    try:
        default, names, truncated = await github.list_branches(user_github_token(user), repo)
    except GitHubError as e:
        raise to_http(e) from e
    return {"default_branch": default, "branches": names, "truncated": truncated}
