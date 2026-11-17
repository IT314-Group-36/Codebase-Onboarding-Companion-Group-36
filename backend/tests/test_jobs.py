"""In-process background jobs (replace arq/Redis), startup recovery, and database URL handling."""
import asyncio

import pytest
from sqlalchemy import select

from app.core.config import Settings, normalize_database_url
from app.db.session import SessionLocal
from app.models import IssueSync, Repository
from app.services import jobs
from app.services.jobs import InProcessQueue, recover_interrupted_jobs

# ---------- database URL handling (Neon / Render hand out plain postgresql:// URLs) ----------

@pytest.mark.parametrize("given, expected", [
    ("postgresql://u:p@localhost/db", "postgresql+psycopg://u:p@localhost/db"),
    ("postgres://u:p@localhost/db", "postgresql+psycopg://u:p@localhost/db"),
    ("postgresql+psycopg://u:p@localhost/db", "postgresql+psycopg://u:p@localhost/db"),
    ("  postgresql://u:p@localhost/db  ", "postgresql+psycopg://u:p@localhost/db"),
    ("postgresql://u:p@ep-a-b-123.us-east-2.aws.neon.tech/neondb",
     "postgresql+psycopg://u:p@ep-a-b-123.us-east-2.aws.neon.tech/neondb?sslmode=require"),
    ("postgresql://u:p@ep-a-b-123.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
     "postgresql+psycopg://u:p@ep-a-b-123.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"),
    ("postgresql://u:p@ep-x.neon.tech/neondb?application_name=app",
     "postgresql+psycopg://u:p@ep-x.neon.tech/neondb?application_name=app&sslmode=require"),
])
def test_database_url_is_normalized(given, expected):
    assert normalize_database_url(given) == expected


def test_settings_apply_the_normalizer(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x.neon.tech/neondb")
    assert Settings().database_url == "postgresql+psycopg://u:p@ep-x.neon.tech/neondb?sslmode=require"


# ---------- the in-process queue ----------

async def test_enqueue_runs_the_job_with_its_arguments(monkeypatch):
    seen = []

    async def job(repo_id, token=None):
        seen.append((repo_id, token))
    monkeypatch.setitem(jobs.JOBS, "sync_issues", job)
    q = InProcessQueue()
    await q.enqueue_job("sync_issues", 7, "tok")
    await asyncio.sleep(0.05)
    assert seen == [(7, "tok")] and not q._tasks               # finished tasks are forgotten


async def test_unknown_job_is_rejected():
    with pytest.raises(ValueError):
        await InProcessQueue().enqueue_job("nope", 1)


async def test_indexing_runs_one_repository_at_a_time(monkeypatch):
    running, peak, finished = 0, 0, []

    async def job(repo_id, token=None):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        finished.append(repo_id)
    monkeypatch.setitem(jobs.JOBS, "index_repository", job)
    q = InProcessQueue(max_indexing=1)
    for i in (1, 2, 3):
        await q.enqueue_job("index_repository", i, None)
    await asyncio.sleep(0.4)
    assert peak == 1 and sorted(finished) == [1, 2, 3]


async def test_two_slots_allow_two_at_once(monkeypatch):
    running, peak = 0, 0

    async def job(repo_id, token=None):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
    monkeypatch.setitem(jobs.JOBS, "index_repository", job)
    q = InProcessQueue(max_indexing=2)
    for i in (1, 2, 3):
        await q.enqueue_job("index_repository", i, None)
    await asyncio.sleep(0.4)
    assert peak == 2


async def test_issue_sync_is_not_blocked_by_a_long_indexing_job(monkeypatch):
    release, synced = asyncio.Event(), []

    async def slow_index(repo_id, token=None):
        await release.wait()

    async def sync(repo_id, token=None):
        synced.append(repo_id)
    monkeypatch.setitem(jobs.JOBS, "index_repository", slow_index)
    monkeypatch.setitem(jobs.JOBS, "sync_issues", sync)
    q = InProcessQueue(max_indexing=1)
    await q.enqueue_job("index_repository", 1, None)
    await q.enqueue_job("sync_issues", 2, None)
    await asyncio.sleep(0.05)
    assert synced == [2]
    release.set()
    await q.aclose()


async def test_aclose_cancels_running_jobs(monkeypatch):
    async def forever(repo_id, token=None):
        await asyncio.sleep(3600)
    monkeypatch.setitem(jobs.JOBS, "index_repository", forever)
    q = InProcessQueue()
    await q.enqueue_job("index_repository", 1, None)
    await asyncio.sleep(0.02)
    await asyncio.wait_for(q.aclose(), 2)
    assert not q._tasks


# ---------- failures are recorded, not lost ----------

async def _make_repo(owner_id, status, url="https://github.com/o/r"):
    async with SessionLocal() as s:
        r = Repository(owner_id=owner_id, url=url, branch="", status=status)
        s.add(r)
        await s.commit()
        return r.id


async def test_a_crashing_index_job_marks_the_repo_failed(db, make_user, monkeypatch):
    user, _ = await make_user()
    rid = await _make_repo(user.id, "queued")

    async def boom(repo_id, token=None):
        raise RuntimeError("boom")
    monkeypatch.setitem(jobs.JOBS, "index_repository", boom)
    q = InProcessQueue()
    await q.enqueue_job("index_repository", rid, None)
    await asyncio.sleep(0.2)
    async with SessionLocal() as s:
        repo = await s.get(Repository, rid)
    assert repo.status == "failed" and "Unexpected error" in repo.error


async def test_a_timed_out_index_job_marks_the_repo_failed(db, make_user, monkeypatch):
    user, _ = await make_user()
    rid = await _make_repo(user.id, "indexing")

    async def slow(repo_id, token=None):
        await asyncio.sleep(3600)
    monkeypatch.setitem(jobs.JOBS, "index_repository", slow)
    q = InProcessQueue(timeout_seconds=0.1)
    await q.enqueue_job("index_repository", rid, None)
    await asyncio.sleep(0.5)
    async with SessionLocal() as s:
        repo = await s.get(Repository, rid)
    assert repo.status == "failed" and "Timed out" in repo.error


# ---------- startup recovery ----------

async def test_startup_recovery_fails_interrupted_jobs_only(db, make_user):
    user, _ = await make_user()
    queued = await _make_repo(user.id, "queued", "https://github.com/o/a")
    indexing = await _make_repo(user.id, "indexing", "https://github.com/o/b")
    ready = await _make_repo(user.id, "ready", "https://github.com/o/c")
    failed = await _make_repo(user.id, "failed", "https://github.com/o/d")
    async with SessionLocal() as s:
        s.add_all([IssueSync(repo_id=queued, status="syncing"), IssueSync(repo_id=ready, status="ok")])
        await s.commit()

    await recover_interrupted_jobs()

    async with SessionLocal() as s:
        status = {r.id: (r.status, r.error) for r in (await s.execute(select(Repository))).scalars()}
        sync = {x.repo_id: x.status for x in (await s.execute(select(IssueSync))).scalars()}
    assert status[queued][0] == status[indexing][0] == "failed" and "interrupted" in status[queued][1]
    assert status[ready] == ("ready", None) and status[failed][0] == "failed"
    assert sync == {queued: "failed", ready: "ok"}


async def test_a_recovered_repo_can_be_reindexed(db, make_user, monkeypatch):
    """Failed repositories accept POST /reindex, so a user is never stuck after a restart."""
    import httpx

    from app.main import app
    from tests.conftest import FakeQueue
    user, headers = await make_user()
    rid = await _make_repo(user.id, "indexing")
    await recover_interrupted_jobs()
    app.state.queue = FakeQueue()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=headers) as c:
        r = await c.post(f"/repos/{rid}/reindex")
    assert r.status_code == 202 and app.state.queue.jobs[-1][0] == "index_repository"


async def test_recovery_survives_a_database_error(monkeypatch):
    class Broken:
        def __call__(self):
            raise RuntimeError("db down")
    monkeypatch.setattr(jobs, "SessionLocal", Broken())
    await recover_interrupted_jobs()                           # logs, does not raise


async def test_lifespan_starts_and_stops_the_real_queue(db):
    from app.main import app, lifespan
    if hasattr(app.state, "queue"):
        del app.state.queue                                    # earlier tests leave a fake behind
    async with lifespan(app):
        assert isinstance(app.state.queue, InProcessQueue)
    assert not hasattr(app.state, "queue")
