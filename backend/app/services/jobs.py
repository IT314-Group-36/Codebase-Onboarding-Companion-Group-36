"""Background jobs that run inside the API process (no Redis, no separate worker).

`InProcessQueue` has the same `enqueue_job(name, *args)` method the API used with arq, so the routes and the
tests' fake queue are unchanged. Indexing runs one repository at a time by default (MAX_CONCURRENT_INDEXING):
cloning, parsing and embedding are memory-heavy and small hosts have little RAM.

Jobs live only in this process. If the server restarts or sleeps mid-job, the job is gone;
`recover_interrupted_jobs` runs at startup and marks such repositories "failed" so the user can re-index.
"""
import asyncio
import logging

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models import IssueSync, Repository
from app.services import runtime
from app.services.indexing import run_indexing
from app.services.issues import run_issue_sync

log = logging.getLogger(__name__)

INTERRUPTED_REPO_MESSAGE = "Indexing was interrupted because the server restarted. Click Re-index to try again."
INTERRUPTED_SYNC_MESSAGE = "The issue sync was interrupted because the server restarted. Please sync again."


async def index_repository(repo_id: int, access_token: str | None = None) -> None:
    await run_indexing(repo_id, access_token, llm=runtime.get_llm(), embedder=runtime.get_embedder())
    async with SessionLocal() as session:
        status = (await session.execute(select(Repository.status).where(Repository.id == repo_id))).scalar_one_or_none()
    if status == "ready":
        try:
            await run_issue_sync(repo_id, access_token)
        except Exception:  # best-effort enrichment; indexing remains successful
            log.exception("issue sync after indexing repo %s failed", repo_id)


async def sync_issues(repo_id: int, access_token: str | None = None) -> None:
    await run_issue_sync(repo_id, access_token)


JOBS = {"index_repository": index_repository, "sync_issues": sync_issues}


async def _mark_failed(name: str, repo_id: int, message: str) -> None:
    """Record a failure the job itself could not (it timed out)."""
    async with SessionLocal() as s:
        if name == "index_repository":
            await s.execute(update(Repository).where(Repository.id == repo_id)
                            .values(status="failed", stage=None, error=message))
        else:
            await s.execute(update(IssueSync).where(IssueSync.repo_id == repo_id)
                            .values(status="failed", message=message))
        await s.commit()


class InProcessQueue:
    def __init__(self, max_indexing: int = 1, timeout_seconds: float = 1800):
        self._timeout = timeout_seconds
        self._indexing_slots = asyncio.Semaphore(max(1, max_indexing))
        self._tasks: set[asyncio.Task] = set()

    async def enqueue_job(self, name: str, *args) -> None:
        job = JOBS.get(name)
        if job is None:
            raise ValueError(f"Unknown job {name!r}")
        task = asyncio.create_task(self._run(name, job, args), name=f"{name}:{args[0] if args else ''}")
        self._tasks.add(task)                      # keep a reference, or the task could be garbage-collected
        task.add_done_callback(self._tasks.discard)

    async def _run(self, name: str, job, args: tuple) -> None:
        try:
            if name == "index_repository":
                async with self._indexing_slots:   # waiting jobs stay "queued" until a slot frees up
                    await asyncio.wait_for(job(*args), self._timeout)
            else:
                await asyncio.wait_for(job(*args), self._timeout)
        except asyncio.TimeoutError:
            log.error("job %s%r timed out after %ss", name, args[:1], self._timeout)
            await self._safe_mark_failed(name, args[0], f"Timed out after {int(self._timeout // 60)} minutes.")
        except Exception:  # noqa: BLE001  (the job functions record their own failures; this is the last resort)
            log.exception("job %s%r crashed", name, args[:1])
            await self._safe_mark_failed(name, args[0], "Unexpected error in the background job. Please try again.")

    @staticmethod
    async def _safe_mark_failed(name: str, repo_id: int, message: str) -> None:
        try:
            await _mark_failed(name, repo_id, message)
        except Exception:  # noqa: BLE001
            log.exception("could not record the failure of %s for repo %s", name, repo_id)

    async def aclose(self) -> None:
        """Server shutting down: stop running jobs (startup recovery marks them failed next time)."""
        tasks = list(self._tasks)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def recover_interrupted_jobs() -> None:
    """At startup nothing can still be running: anything left queued/indexing/syncing was cut off by a restart."""
    try:
        async with SessionLocal() as s:
            repos = await s.execute(update(Repository).where(Repository.status.in_(("queued", "indexing")))
                                    .values(status="failed", stage=None, error=INTERRUPTED_REPO_MESSAGE))
            syncs = await s.execute(update(IssueSync).where(IssueSync.status.in_(("queued", "syncing")))
                                    .values(status="failed", message=INTERRUPTED_SYNC_MESSAGE))
            await s.commit()
        if repos.rowcount or syncs.rowcount:
            log.warning("marked %s interrupted indexing job(s) and %s issue sync(s) as failed",
                        repos.rowcount, syncs.rowcount)
    except Exception:  # noqa: BLE001  (a database hiccup must not stop the API from starting)
        log.exception("could not check for interrupted jobs at startup")
