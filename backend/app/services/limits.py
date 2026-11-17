"""Quotas that keep the free tiers (Neon storage, Cloudflare embeddings, Render RAM) from being used up.

Request-rate limits live in app/core/ratelimit.py; these are about how much a user may keep and run at once.
The checks are not locked against each other, so two simultaneous requests can overshoot a limit by one:
that is fine for a safeguard.
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Chunk, Repository

ACTIVE_STATUSES = ("queued", "indexing")


async def total_chunks(session: AsyncSession, exclude_repo_id: int | None = None) -> int:
    """Chunks stored for all users together (the part of the database that grows: text + a 384-number vector each)."""
    stmt = select(func.count()).select_from(Chunk)
    if exclude_repo_id is not None:
        stmt = stmt.where(Chunk.repo_id != exclude_repo_id)
    return (await session.execute(stmt)).scalar_one()


def storage_full_message(used_by_others: int, needed: int) -> str:
    return (f"The server's free storage is full ({used_by_others:,} of {get_settings().max_total_chunks:,} code chunks "
            f"are used by other repositories and this one needs {needed:,}), so it was not indexed. Delete a repository "
            "you no longer need, or try a smaller one.")


async def check_can_add_repo(session: AsyncSession, user_id: int) -> None:
    """Called before a NEW repository is created. Raises HTTPException when the account or the server is at its limit."""
    cfg = get_settings()
    owned = (await session.execute(
        select(func.count()).select_from(Repository).where(Repository.owner_id == user_id))).scalar_one()
    if owned >= cfg.max_repos_per_user:
        raise HTTPException(403, f"You can keep up to {cfg.max_repos_per_user} repositories. "
                                 "Delete one you no longer need to add another.")
    await check_job_slot(session, user_id)
    if await total_chunks(session) >= cfg.max_total_chunks:
        raise HTTPException(503, "The server's free storage is full, so no new repositories can be added right now. "
                                 "Please try again later.")


async def check_job_slot(session: AsyncSession, user_id: int) -> None:
    """Called before indexing work is queued: one account cannot fill the (one-at-a-time) indexing queue."""
    cfg = get_settings()
    active = (await session.execute(
        select(func.count()).select_from(Repository).where(
            Repository.owner_id == user_id, Repository.status.in_(ACTIVE_STATUSES)))).scalar_one()
    if active >= cfg.max_active_jobs_per_user:
        raise HTTPException(429, f"You already have {active} repositories waiting to be indexed or being indexed. "
                                 "Wait for one to finish, then try again.")
