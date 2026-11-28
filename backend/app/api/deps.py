from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ratelimit import enforce_index, enforce_llm, enforce_read, enforce_write
from app.core.security import read_session
from app.db.session import get_session
from app.models import Repository, User
from app.services import runtime
from app.services.github import GitHubClient


def get_queue(request: Request):
    return request.app.state.queue


def get_llm_dep():
    return runtime.get_llm()


def get_embedder_dep():
    return runtime.get_embedder()


def get_github_client() -> GitHubClient:
    return GitHubClient()


# ---------- authentication and ownership ----------
# Every /repos route uses get_user_repo / get_ready_user_repo, so a user only ever sees their own repositories.

async def get_optional_user(request: Request, session: AsyncSession = Depends(get_session)) -> User | None:
    """The signed-in user from the session cookie, or None (no cookie, forged, expired, user deleted, or logged out).

    The cookie carries the session version it was issued under; it is accepted only while that equals the user's current
    session_version, so logout (which raises the number) cuts off every copy of the cookie at once.
    """
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    data = read_session(token)
    if data is None:
        return None
    user_id, version = data
    user = await session.get(User, user_id)
    if user is None or user.session_version != version:
        return None
    return user


async def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return user


async def get_user_repo(repo_id: int, user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)) -> Repository:
    """A repository the signed-in user owns. Someone else's repo answers 404, the same as a missing one,
    so ids cannot be probed."""
    repo = await session.get(Repository, repo_id)
    if repo is None or repo.owner_id != user.id:
        raise HTTPException(404, "Repository not found")
    return repo


async def get_ready_user_repo(repo: Repository = Depends(get_user_repo)) -> Repository:
    if repo.status != "ready":
        raise HTTPException(409, f"Repository is not ready (status: {repo.status})")
    return repo


# ---------- per-user rate limits ----------
# Each one signs the user in (401 when not), counts the request against a bucket (429 + Retry-After when the user is
# over it) and returns the user, so a route can use it in place of get_current_user.

async def limit_llm(user: User = Depends(get_current_user)) -> User:
    enforce_llm(user.id)
    return user


async def limit_read(user: User = Depends(get_current_user)) -> User:
    enforce_read(user.id)
    return user


async def limit_index(user: User = Depends(get_current_user)) -> User:
    enforce_index(user.id)
    return user


async def limit_write(user: User = Depends(get_current_user)) -> User:
    enforce_write(user.id)
    return user
