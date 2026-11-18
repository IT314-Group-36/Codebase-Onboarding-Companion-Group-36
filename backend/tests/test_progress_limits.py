"""Only real tasks can allocate progress rows; writes and storage are bounded."""
import asyncio

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import TaskProgress
from tests.test_api import client, index  # noqa: F401
from tests.test_onboarding_progress import add_issue, plan, put


async def progress_count():
    async with SessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(TaskProgress))


@pytest.mark.parametrize("key", ["gen-invented-task-1", "issue-999", "issue-0007"])
async def test_invented_or_noncanonical_keys_allocate_nothing(client, git_repo, key):
    rid = await index(client, git_repo)
    await add_issue(rid, 7)
    assert (await put(client, rid, key, "completed")).status_code == 404
    assert await progress_count() == 0


async def test_ineligible_issues_cannot_be_used_as_tasks(client, git_repo):
    rid = await index(client, git_repo)
    await add_issue(rid, 1, labels=("hard",))
    assert (await put(client, rid, "issue-1", "completed")).status_code == 404
    assert await progress_count() == 0


async def test_real_generated_task_needs_no_embeddings_or_ai_to_validate(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    key = (await plan(client, rid))["tasks"][0]["key"]
    from app.services import tasks
    monkeypatch.setattr(tasks, "hybrid_search", lambda *a, **k: pytest.fail("No embedding calls on progress writes"))
    assert (await put(client, rid, key, "completed")).status_code == 200
    assert await progress_count() == 1


async def test_progress_write_rate_limit_is_separate_from_read_and_ai(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    await add_issue(rid, 1)
    monkeypatch.setattr(get_settings(), "rate_limit_write_per_minute", 2)
    assert (await put(client, rid, "issue-1", "completed")).status_code == 200
    assert (await put(client, rid, "issue-1", "in-progress")).status_code == 200
    refused = await put(client, rid, "issue-1", "completed")
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) >= 1
    assert (await client.get(f"/repos/{rid}/onboarding-tasks")).status_code == 200
    assert await progress_count() == 1


async def test_per_repo_cap_allows_updates_and_reset_frees_a_slot(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    await add_issue(rid, 1)
    await add_issue(rid, 2)
    monkeypatch.setattr(get_settings(), "max_task_progress_per_repo", 1)
    assert (await put(client, rid, "issue-1", "completed")).status_code == 200
    assert (await put(client, rid, "issue-2", "completed")).status_code == 403
    assert (await put(client, rid, "issue-1", "in-progress")).status_code == 200
    assert (await put(client, rid, "issue-1", "pending")).status_code == 200
    assert await progress_count() == 0
    assert (await put(client, rid, "issue-2", "completed")).status_code == 200


async def test_global_progress_cap_applies_across_repositories(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    other = await index(client, git_repo, branch="main")
    await add_issue(rid, 1)
    await add_issue(other, 1)
    monkeypatch.setattr(get_settings(), "max_total_task_progress", 1)
    assert (await put(client, rid, "issue-1", "completed")).status_code == 200
    assert (await put(client, other, "issue-1", "completed")).status_code == 503
    assert await progress_count() == 1


async def test_concurrent_progress_creates_cannot_overshoot_cap(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    await add_issue(rid, 1)
    await add_issue(rid, 2)
    monkeypatch.setattr(get_settings(), "max_task_progress_per_repo", 1)
    results = await asyncio.gather(
        put(client, rid, "issue-1", "completed"), put(client, rid, "issue-2", "completed"),
    )
    assert sorted(result.status_code for result in results) == [200, 403]
    assert await progress_count() == 1
