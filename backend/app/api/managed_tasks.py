"""Durable task management endpoints; legacy onboarding routes remain compatible."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from app.models import File
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ready_user_repo, limit_read, limit_write, get_llm_dep
from app.core.ratelimit import enforce_llm
from app.db.session import get_session
from app.models import ManagedTask, Repository, User, IssueSync
from app.services.issues import sync_view
from app.services.task_manager import as_dict, create_task, generate, lock_scope, similar, stored_tasks, sync_cached_issues, normalize

router = APIRouter(prefix='/repos', tags=['managed-tasks'])

class TaskCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    difficulty: Literal['easy', 'medium', 'hard'] = 'easy'
    related_files: list[str] = Field(default_factory=list, max_length=20)

    @field_validator('title', 'description')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Must not be blank')
        return value.strip()

    @field_validator('related_files')
    @classmethod
    def paths(cls, value):
        if any(not p or len(p) > 500 or p.startswith('/') or '..' in p.split('/') for p in value):
            raise ValueError('Invalid relative file path')
        return list(dict.fromkeys(value))

class TaskEdit(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    difficulty: Literal['easy', 'medium', 'hard'] | None = None
    related_files: list[str] | None = Field(default=None, max_length=20)
    status: Literal['pending', 'in-progress', 'completed'] | None = None

    @field_validator('title', 'description')
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError('Must not be blank')
        return value.strip() if value is not None else None

    @field_validator('related_files')
    @classmethod
    def paths(cls, value):
        return TaskCreate.paths(value) if value is not None else None

async def validate_related_files(session, repo_id: int, paths: list[str] | None):
    if not paths:
        return
    allowed = set((await session.execute(select(File.path).where(
        File.repo_id == repo_id, File.sensitive.is_(False), File.path.in_(paths)))).scalars().all())
    if any(path not in allowed for path in paths):
        raise HTTPException(422, 'Related files must exist in the indexed repository and not be sensitive')


async def owned_task(session, user, repo, key):
    task = await session.scalar(select(ManagedTask).where(ManagedTask.user_id == user.id,
                            ManagedTask.repo_id == repo.id, ManagedTask.key == key,
                            ManagedTask.deleted.is_(False)))
    if task is None:
        raise HTTPException(404, 'Task not found')
    return task

@router.get('/{repo_id}/tasks')
async def list_tasks(repo: Repository = Depends(get_ready_user_repo), user: User = Depends(limit_read),
                     session: AsyncSession = Depends(get_session)):
    await lock_scope(session, user.id, repo.id)
    await sync_cached_issues(session, user.id, repo.id)
    rows = await stored_tasks(session, user.id, repo.id)
    await session.commit()
    return {'tasks': [as_dict(t) for t in rows], 'sync': sync_view(await session.get(IssueSync, repo.id))}

@router.post('/{repo_id}/tasks', status_code=201)
async def add_task(body: TaskCreate, repo: Repository = Depends(get_ready_user_repo),
                   user: User = Depends(limit_write), session: AsyncSession = Depends(get_session)):
    await validate_related_files(session, repo.id, body.related_files)
    return await create_task(session, user.id, repo.id, body)

@router.post('/{repo_id}/tasks/generate', status_code=201)
async def generate_tasks(repo: Repository = Depends(get_ready_user_repo), user: User = Depends(limit_write),
                         session: AsyncSession = Depends(get_session), llm=Depends(get_llm_dep)):
    enforce_llm(user.id)
    return {'tasks': await generate(session, user.id, repo, llm)}

@router.patch('/{repo_id}/tasks/{task_key}')
async def edit_task(task_key: str, body: TaskEdit, repo: Repository = Depends(get_ready_user_repo),
                    user: User = Depends(limit_write), session: AsyncSession = Depends(get_session)):
    await lock_scope(session, user.id, repo.id)
    t = await owned_task(session, user, repo, task_key)
    changes = body.model_dump(exclude_unset=True)
    if t.source != 'manual' and any(k in changes for k in ('title', 'description', 'difficulty', 'related_files')):
        raise HTTPException(403, 'Only manually created tasks can be edited; all tasks support status updates')
    if 'related_files' in changes:
        await validate_related_files(session, repo.id, changes['related_files'])
    if 'title' in changes:
        others = await stored_tasks(session, user.id, repo.id, include_deleted=True)
        if any(other.id != t.id and similar(other.title, changes['title']) for other in others):
            raise HTTPException(409, 'A similar task already exists in this repository history')
        changes['fingerprint'] = normalize(changes['title'])
    for key, value in changes.items():
        if value is None:
            raise HTTPException(422, f'{key} cannot be null')
        setattr(t, key, value)
    await session.commit()
    return as_dict(t)

@router.delete('/{repo_id}/tasks/{task_key}', status_code=204)
async def delete_task(task_key: str, repo: Repository = Depends(get_ready_user_repo),
                      user: User = Depends(limit_write), session: AsyncSession = Depends(get_session)):
    await lock_scope(session, user.id, repo.id)
    t = await owned_task(session, user, repo, task_key)
    if t.source != 'manual':
        raise HTTPException(403, 'Only manually created tasks may be deleted')
    t.deleted = True  # Tombstone remains to prevent later AI generation of the same task.
    await session.commit()
