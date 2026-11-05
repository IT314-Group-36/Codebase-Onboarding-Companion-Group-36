from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Repository
from app.services import runtime


async def get_repo(repo_id: int, session: AsyncSession = Depends(get_session)) -> Repository:
    repo = await session.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(404, "Repository not found")
    return repo


async def get_ready_repo(repo: Repository = Depends(get_repo)) -> Repository:
    if repo.status != "ready":
        raise HTTPException(409, f"Repository is not ready (status: {repo.status})")
    return repo


def get_queue(request: Request):
    return request.app.state.queue


def get_llm_dep():
    return runtime.get_llm()


def get_embedder_dep():
    return runtime.get_embedder()
