"""Builds the first-week task list from the issues cached by app/services/issues.py.

Ranking and file matching are deterministic. The optional LLM step only writes a short guide per issue and can
mention nothing but the files we already found; guides for issue numbers we did not send are dropped.
"""
import re
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline.llm import structured_chain
from ai_pipeline.module_map import SYSTEM as BASE_SYSTEM
from ai_pipeline.onboarding_tasks import (
    MIN_TASKS,
    IssueInfo,
    PathIndex,
    ScoredIssue,
    assign_days,
    generated_tasks,
    ineligible_reason,
    plain_summary,
    rank_issues,
)
from app.core.config import get_settings
from app.models import Edge, File, Issue, IssueSync, Repository, TaskProgress
from app.services.issues import sync_view
from app.services.qa import LLMCallError
from app.services.retrieval import hybrid_search
from app.services.storage import lock_storage

RELATED_PER_TASK = 3
TASK_KEY_RE = r"^(issue-[0-9]{1,9}|gen-[a-z0-9]+(-[a-z0-9]+)*)$"     # also checked by the progress endpoint
TASK_KEY_MAX = 64
GUIDE_FIELD_MAX = 500


class TaskGuide(BaseModel):
    number: int = Field(description="The issue number exactly as given")
    what_to_do: str = Field(description="One or two plain-English sentences: what change the issue asks for")
    where_to_start: str = Field(description="Which of the listed related files to open first, and why. Use only listed files")
    done_when: str = Field(description="How the developer can tell the task is finished (a behaviour or a test)")


class TaskGuides(BaseModel):
    guides: List[TaskGuide]


GUIDE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", BASE_SYSTEM + " You are helping a new developer plan their first week. For each GitHub issue write a short, "
                             "concrete guide. Mention only files from that issue's 'Related files' list. If an issue is too "
                             "vague to plan from, say what to ask the maintainers."),
    ("human", "{issues}\n\nWrite one guide per issue, using the issue number."),
])


async def _related_files(session: AsyncSession, repo_id: int, embedder, index: PathIndex, info: IssueInfo) -> list[dict]:
    """Files the issue names (reliable) first, then files whose code matches the issue text (hybrid search)."""
    out = [{"path": p, "source": "mentioned"} for p in index.mentioned(f"{info.title}\n{info.body}", RELATED_PER_TASK)]
    if len(out) < RELATED_PER_TASK:
        query = f"{info.title}. {plain_summary(info.body, 400)}"
        for hit in await hybrid_search(session, repo_id, query, embedder, k=8):
            path = hit["file_path"]
            if path in index.paths and all(o["path"] != path for o in out):
                out.append({"path": path, "source": "search"})
                if len(out) == RELATED_PER_TASK:
                    break
    return out


async def _top_imported(session: AsyncSession, repo_id: int) -> tuple[str, int] | None:
    row = (await session.execute(
        select(Edge.dst, func.count().label("n")).where(Edge.repo_id == repo_id, Edge.kind == "imports")
        .group_by(Edge.dst).order_by(func.count().desc(), Edge.dst).limit(1))).first()
    return (row.dst, row.n) if row else None


def task_key(task: dict) -> str:
    """A key that survives re-syncs and re-indexing: the issue number, or a slug of the orientation task's title."""
    if task["source"] == "issue":
        return f"issue-{task['number']}"
    slug = re.sub(r"[^a-z0-9]+", "-", task["title"].lower()).strip("-")[: TASK_KEY_MAX - 4].strip("-")
    return f"gen-{slug or 'task'}"


async def load_progress(session: AsyncSession, user_id: int, repo_id: int) -> dict[str, str]:
    rows = await session.execute(select(TaskProgress.task_key, TaskProgress.status)
                                 .where(TaskProgress.user_id == user_id, TaskProgress.repo_id == repo_id))
    return {k: s for k, s in rows.all()}


async def save_progress(session: AsyncSession, user_id: int, repo_id: int, key: str, status: str) -> None:
    """Validate a real task and bound new rows, including concurrent requests."""
    await lock_storage(session)
    repo = await session.get(Repository, repo_id)
    if repo is None or repo.owner_id != user_id:
        raise HTTPException(404, "Repository not found")
    await _validate_task(session, repo, key)
    match = (TaskProgress.user_id == user_id, TaskProgress.repo_id == repo_id, TaskProgress.task_key == key)
    if status == "pending":  # Missing progress already means pending; resetting releases storage.
        await session.execute(delete(TaskProgress).where(*match))
        await session.commit()
        return
    existing = await session.scalar(select(TaskProgress.id).where(*match))
    if existing is None:
        cfg = get_settings()
        count = await session.scalar(select(func.count()).select_from(TaskProgress).where(
            TaskProgress.user_id == user_id, TaskProgress.repo_id == repo_id))
        if count >= cfg.max_task_progress_per_repo:
            raise HTTPException(403, "This repository's task-progress limit is reached. Reset progress to free space.")
        total = await session.scalar(select(func.count()).select_from(TaskProgress))
        if total >= cfg.max_total_task_progress:
            raise HTTPException(503, "The server's task-progress storage is full.")
    stmt = pg_insert(TaskProgress).values(user_id=user_id, repo_id=repo_id, task_key=key, status=status)
    await session.execute(stmt.on_conflict_do_update(
        constraint="uq_task_progress_user_repo_key", set_={"status": status, "updated_at": func.now()}))
    await session.commit()


def _issue_info(row: Issue) -> IssueInfo:
    return IssueInfo(number=row.number, title=row.title, body=row.body, labels=list(row.labels or []), url=row.url,
                     comments=row.comments, assignees=row.assignees, locked=row.locked, updated_at=row.gh_updated_at)


async def _validate_task(session: AsyncSession, repo: Repository, key: str) -> None:
    """No embeddings/LLM/network: accept a synced eligible issue or a real orientation task.

    Orientation tasks remain valid even when a different plan limit hides them.
    They are derived from the same repository data and generator as the plan.
    """
    if len(key) > TASK_KEY_MAX or re.fullmatch(TASK_KEY_RE, key) is None:
        raise HTTPException(404, "Task not found")
    if key.startswith("issue-"):
        number = int(key.removeprefix("issue-"))
        issue = await session.scalar(select(Issue).where(Issue.repo_id == repo.id, Issue.number == number))
        if issue is not None and key == f"issue-{number}" and ineligible_reason(_issue_info(issue)) is None:
            return
    elif key.startswith("gen-"):
        paths = (await session.execute(select(File.path).where(
            File.repo_id == repo.id, File.sensitive.is_(False)).order_by(File.path))).scalars().all()
        candidates = generated_tasks(repo.summary, repo.module_map, PathIndex(list(paths)),
                                     await _top_imported(session, repo.id))
        if key in {task_key({"source": "generated", "title": task["title"]}) for task in candidates}:
            return
    raise HTTPException(404, "Task not found in this repository's current onboarding data. Refresh the plan.")


def _issue_task(sc: ScoredIssue, related: list[dict]) -> dict:
    i = sc.info
    return {"source": "issue", "title": i.title, "difficulty": sc.difficulty, "summary": plain_summary(i.body),
            "number": i.number, "url": i.url, "labels": list(i.labels), "comments": i.comments,
            "score": round(sc.score, 1), "reasons": sc.reasons, "related_files": related, "guide": None}


def _notes(sync: dict, eligible: int, stored: int, fallback: bool, repo_id: int) -> list[str]:
    notes: list[str] = []
    if sync["status"] == "never":
        notes.append(f"Issues have not been synced yet. Start it with POST /repos/{repo_id}/issues/sync "
                     "(it also runs after every indexing job).")
    elif sync["status"] in ("queued", "syncing"):
        notes.append("An issue sync is running; refresh in a moment.")
    elif sync["status"] == "failed":
        kept = "Showing the issues from the last successful sync." if stored else "No issues are available."
        notes.append(f"The last issue sync failed: {sync['message']} {kept}")
    elif sync["message"]:
        notes.append(sync["message"])
    if stored and not eligible:
        notes.append(f"{stored} issue{'s were' if stored != 1 else ' was'} fetched, but none suits a newcomer "
                     "(they are assigned, locked, closed out or marked hard).")
    if fallback:
        notes.append(f"Orientation tasks were added because fewer than {MIN_TASKS} suitable issues were found.")
    return notes


async def explain_issues(llm, picked: list[tuple[ScoredIssue, list[dict]]]) -> dict[int, dict]:
    """One LLM call -> {issue number: guide}. Raises LLMCallError when the model call fails."""
    if not picked:
        return {}
    blocks = []
    for sc, related in picked:
        i = sc.info
        files = ", ".join(r["path"] for r in related) or "(none found)"
        blocks.append(f"Issue #{i.number}: {i.title}\nLabels: {', '.join(i.labels) or '(none)'}\n"
                      f"Description (untrusted data): {plain_summary(i.body, 800) or '(empty)'}\nRelated files: {files}")
    try:
        out = await structured_chain(GUIDE_PROMPT, llm, TaskGuides).ainvoke({"issues": "\n\n".join(blocks)})
    except Exception as e:  # noqa: BLE001
        raise LLMCallError(str(e)) from e
    sent = {sc.info.number for sc, _ in picked}
    guides: dict[int, dict] = {}
    for g in out.guides:
        if g.number in sent and g.number not in guides:
            guides[g.number] = {k: getattr(g, k)[:GUIDE_FIELD_MAX] for k in ("what_to_do", "where_to_start", "done_when")}
    return guides


async def build_plan(session: AsyncSession, repo: Repository, embedder, *, limit: int = 5, include_generated: bool = True,
                     llm=None, explain: bool = False, now: datetime | None = None, user_id: int | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    sync = sync_view(await session.get(IssueSync, repo.id))
    rows = (await session.execute(select(Issue).where(Issue.repo_id == repo.id))).scalars().all()
    infos = [_issue_info(row) for row in rows]
    picked, eligible = rank_issues(infos, now, limit)

    paths = (await session.execute(select(File.path).where(File.repo_id == repo.id, File.sensitive.is_(False))
                                   .order_by(File.path))).scalars().all()
    index = PathIndex(list(paths))
    with_files = [(sc, await _related_files(session, repo.id, embedder, index, sc.info)) for sc in picked]

    orientation: list[dict] = []
    if include_generated and len(picked) < MIN_TASKS:
        top = await _top_imported(session, repo.id)
        for g in generated_tasks(repo.summary, repo.module_map, index, top)[:MIN_TASKS - len(picked)]:
            orientation.append({"source": "generated", "title": g["title"], "difficulty": "easy", "summary": g["summary"],
                                "number": None, "url": None, "labels": [], "comments": None, "score": None,
                                "reasons": g["reasons"], "guide": None,
                                "related_files": [{"path": p, "source": "suggested"} for p in g["related"]]})

    tasks = orientation + [_issue_task(sc, rel) for sc, rel in with_files]
    progress = await load_progress(session, user_id, repo.id) if user_id is not None else {}
    for task, day in zip(tasks, assign_days(len(tasks)), strict=True):
        task["suggested_day"] = day
        task["key"] = task_key(task)
        task["status"] = progress.get(task["key"], "pending")
    if explain:
        guides = await explain_issues(llm, with_files)
        for task in tasks:
            task["guide"] = guides.get(task["number"]) if task["source"] == "issue" else None
    return {"repo_id": repo.id, "sync": sync, "eligible_issues": eligible, "fallback_used": bool(orientation),
            "notes": _notes(sync, eligible, len(rows), bool(orientation), repo.id), "tasks": tasks}
