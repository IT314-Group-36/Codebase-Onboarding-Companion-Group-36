"""First-week task list: sync GitHub issues, then ask for the plan."""
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_embedder_dep,
    get_llm_dep,
    get_queue,
    get_ready_user_repo,
    get_user_repo,
    limit_index,
    limit_read,
)
from app.core.ratelimit import enforce_llm
from app.db.session import get_session
from app.models import IssueSync, Repository, User
from app.schemas import ReindexIn, SyncOut, TaskPlanOut, TaskProgressIn, TaskProgressOut
from app.services.issues import mark_sync, sync_in_progress, sync_view
from app.services.qa import LLMCallError
from app.services.tasks import TASK_KEY_MAX, TASK_KEY_RE, build_plan, save_progress

router = APIRouter(prefix="/repos", tags=["onboarding-tasks"])


@router.post("/{repo_id}/issues/sync", response_model=SyncOut, status_code=202)
async def sync_issues(body: ReindexIn | None = None, repo: Repository = Depends(get_user_repo), _user: User = Depends(limit_index),
                      session: AsyncSession = Depends(get_session), queue=Depends(get_queue)):
    """Fetch the repo's beginner-friendly open issues from GitHub (background job). The token is used for this job only."""
    if sync_in_progress(await session.get(IssueSync, repo.id)):
        raise HTTPException(409, "An issue sync is already in progress")
    await mark_sync(session, repo.id, status="queued", message=None)
    await session.commit()
    await queue.enqueue_job("sync_issues", repo.id, body.access_token if body else None)
    return sync_view(await session.get(IssueSync, repo.id, populate_existing=True))


@router.get("/{repo_id}/issues/sync", response_model=SyncOut)
async def issue_sync_status(repo: Repository = Depends(get_user_repo), session: AsyncSession = Depends(get_session)):
    """Cheap status check to poll after POST /issues/sync."""
    return sync_view(await session.get(IssueSync, repo.id))


@router.get("/{repo_id}/onboarding-tasks", response_model=TaskPlanOut)
async def onboarding_tasks(limit: int = Query(5, ge=1, le=10, description="Maximum number of issue tasks"),
                           include_generated: bool = Query(True, description="Add orientation tasks when few issues qualify"),
                           explain: bool = Query(False, description="Add a short LLM-written guide to each issue task"),
                           repo: Repository = Depends(get_ready_user_repo), user: User = Depends(limit_read),
                           session: AsyncSession = Depends(get_session),
                           embedder=Depends(get_embedder_dep), llm=Depends(get_llm_dep)):
    """A first-week plan: the best beginner-friendly issues, easiest first, each with the files to open.
    Every task carries its stable `key` and the signed-in user's saved `status`."""
    if explain and llm is None:
        raise HTTPException(503, "LLM is not configured (set LLM_API_KEY). The plan itself works without it.")
    if explain:
        enforce_llm(user.id)
    try:
        return await build_plan(session, repo, embedder, limit=limit, include_generated=include_generated,
                                llm=llm, explain=explain, user_id=user.id)
    except LLMCallError as e:
        raise HTTPException(502, f"The LLM call failed: {str(e)[:300]}") from e


@router.put("/{repo_id}/onboarding-tasks/{task_key}/progress", response_model=TaskProgressOut)
async def set_task_progress(body: TaskProgressIn,
                            task_key: str = Path(pattern=TASK_KEY_RE, max_length=TASK_KEY_MAX),
                            repo: Repository = Depends(get_user_repo), user: User = Depends(get_current_user),
                            session: AsyncSession = Depends(get_session)):
    """Save the signed-in user's progress on one task (pending, in-progress or completed). Progress is per user."""
    await save_progress(session, user.id, repo.id, task_key, body.status)
    return {"key": task_key, "status": body.status}
