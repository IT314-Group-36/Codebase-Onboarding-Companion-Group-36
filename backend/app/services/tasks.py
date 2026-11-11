"""Builds the first-week task list from the issues cached by app/services/issues.py.

Ranking and file matching are deterministic. The optional LLM step only writes a short guide per issue and can
mention nothing but the files we already found; guides for issue numbers we did not send are dropped.
"""
from datetime import datetime, timezone
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from sqlalchemy import func, select
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
    plain_summary,
    rank_issues,
)
from app.models import Edge, File, Issue, IssueSync, Repository
from app.services.issues import sync_view
from app.services.qa import LLMCallError
from app.services.retrieval import hybrid_search

RELATED_PER_TASK = 3
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
                     llm=None, explain: bool = False, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    sync = sync_view(await session.get(IssueSync, repo.id))
    rows = (await session.execute(select(Issue).where(Issue.repo_id == repo.id))).scalars().all()
    infos = [IssueInfo(number=r.number, title=r.title, body=r.body, labels=list(r.labels or []), url=r.url,
                       comments=r.comments, assignees=r.assignees, locked=r.locked, updated_at=r.gh_updated_at)
             for r in rows]
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
    for task, day in zip(tasks, assign_days(len(tasks)), strict=True):
        task["suggested_day"] = day
    if explain:
        guides = await explain_issues(llm, with_files)
        for task in tasks:
            task["guide"] = guides.get(task["number"]) if task["source"] == "issue" else None
    return {"repo_id": repo.id, "sync": sync, "eligible_issues": eligible, "fallback_used": bool(orientation),
            "notes": _notes(sync, eligible, len(rows), bool(orientation), repo.id), "tasks": tasks}
