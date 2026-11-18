"""Person 5: onboarding progress is saved on the server, per user, and the plan carries stable task keys."""
import re
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.main import app
from app.models import Issue, TaskProgress
from app.services.runtime import get_embedder
from app.services.tasks import TASK_KEY_MAX, TASK_KEY_RE, build_plan, task_key
from tests.test_api import client, index  # noqa: F401  (client is a fixture)


async def add_issue(repo_id, number, title="Fix typo in payments docs", labels=("good first issue",)):
    async with SessionLocal() as s:
        s.add(Issue(repo_id=repo_id, number=number, title=title, labels=list(labels), url=f"https://x/issues/{number}",
                    body="The refund text in shop/payments.py has a typo. Please fix the wording and update the docs.",
                    comments=1, assignees=0, locked=False, gh_updated_at=datetime.now(timezone.utc)))
        await s.commit()


async def plan(client, rid):
    r = await client.get(f"/repos/{rid}/onboarding-tasks")
    assert r.status_code == 200, r.text
    return r.json()


async def put(client, rid, key, status):
    return await client.put(f"/repos/{rid}/onboarding-tasks/{key}/progress", json={"status": status})


# ---------- keys ----------

def test_task_keys_are_stable_and_valid():
    issue = {"source": "issue", "number": 42, "title": "anything"}
    assert task_key(issue) == "issue-42"
    gen = {"source": "generated", "title": "Read the entry point shop/api.py"}
    assert task_key(gen) == "gen-read-the-entry-point-shop-api-py"
    assert task_key(gen) == task_key(dict(gen))                              # same title -> same key
    long = {"source": "generated", "title": "Explore the " + "very-long-module-name " * 12 + "module"}
    assert len(task_key(long)) <= TASK_KEY_MAX and re.match(TASK_KEY_RE, task_key(long))
    assert re.match(TASK_KEY_RE, task_key({"source": "generated", "title": "!!!"}))      # nothing usable -> gen-task


# ---------- plan carries key + status ----------

async def test_plan_has_keys_and_everything_starts_pending(client, git_repo):
    rid = await index(client, git_repo)
    tasks = (await plan(client, rid))["tasks"]
    assert tasks, "orientation tasks are added when there are no issues"
    keys = [t["key"] for t in tasks]
    assert len(set(keys)) == len(keys) and all(re.match(TASK_KEY_RE, k) for k in keys)
    assert all(t["status"] == "pending" for t in tasks)                      # no pre-completed defaults


async def test_saved_progress_comes_back_in_the_plan(client, git_repo):
    rid = await index(client, git_repo)
    await add_issue(rid, 7)
    tasks = (await plan(client, rid))["tasks"]
    issue = next(t for t in tasks if t["source"] == "issue")
    assert issue["key"] == "issue-7"
    other = next(t for t in tasks if t["source"] == "generated")

    r = await put(client, rid, issue["key"], "completed")
    assert r.status_code == 200 and r.json() == {"key": "issue-7", "status": "completed"}
    assert (await put(client, rid, other["key"], "in-progress")).status_code == 200

    after = {t["key"]: t["status"] for t in (await plan(client, rid))["tasks"]}
    assert after["issue-7"] == "completed" and after[other["key"]] == "in-progress"
    assert sum(1 for s in after.values() if s != "pending") == 2             # the rest are untouched


async def test_progress_can_be_changed_back_and_is_one_row(client, git_repo):
    rid = await index(client, git_repo)
    await add_issue(rid, 1)
    for status in ("completed", "pending", "in-progress", "completed"):
        assert (await put(client, rid, "issue-1", status)).status_code == 200
    async with SessionLocal() as s:
        rows = (await s.execute(select(TaskProgress).where(TaskProgress.repo_id == rid))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "completed" and rows[0].task_key == "issue-1"


# ---------- validation ----------

@pytest.mark.parametrize("key", ["issue-abc", "gen-", "gen-Bad_Key", "../etc/passwd", "task-1", "issue-"])
async def test_bad_task_keys_are_rejected(client, git_repo, key):
    rid = await index(client, git_repo)
    assert (await put(client, rid, key, "completed")).status_code in (404, 422)
    async with SessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(TaskProgress))).scalar_one() == 0


async def test_bad_status_is_rejected(client, git_repo):
    rid = await index(client, git_repo)
    for bad in ("done", "COMPLETED", "", None):
        r = await client.put(f"/repos/{rid}/onboarding-tasks/issue-1/progress", json={"status": bad})
        assert r.status_code == 422
    assert (await client.put(f"/repos/{rid}/onboarding-tasks/issue-1/progress", json={})).status_code == 422


# ---------- privacy ----------

async def test_progress_is_per_user_and_private(client, git_repo, make_user):
    rid = await index(client, git_repo)
    await add_issue(rid, 5)
    assert (await put(client, rid, "issue-5", "completed")).status_code == 200

    _, headers2 = await make_user(github_id=2, login="other")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=headers2) as c2:
        # another user cannot read or write progress on a repository they do not own (same 404 as a missing one)
        assert (await put(c2, rid, "issue-5", "pending")).status_code == 404
        assert (await c2.get(f"/repos/{rid}/onboarding-tasks")).status_code == 404

    # and the plan for a different user id never shows this user's rows
    async with SessionLocal() as s:
        from app.models import Repository
        repo = await s.get(Repository, rid)
        mine = await build_plan(s, repo, get_embedder(), user_id=client.user.id)
        theirs = await build_plan(s, repo, get_embedder(), user_id=client.user.id + 999)
    assert {t["key"]: t["status"] for t in mine["tasks"]}["issue-5"] == "completed"
    assert {t["key"]: t["status"] for t in theirs["tasks"]}["issue-5"] == "pending"      # same repo, other user id
    async with SessionLocal() as s:
        rows = (await s.execute(select(TaskProgress.user_id))).scalars().all()
    assert rows == [client.user.id]                                                      # the 404 write saved nothing


async def test_unauthenticated_requests_are_refused(client, git_repo):
    rid = await index(client, git_repo)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as anon:
        assert (await put(anon, rid, "issue-1", "completed")).status_code == 401
        assert (await anon.get(f"/repos/{rid}/onboarding-tasks")).status_code == 401


async def test_progress_is_deleted_with_the_repository(client, git_repo):
    rid = await index(client, git_repo)
    await add_issue(rid, 1)
    assert (await put(client, rid, "issue-1", "completed")).status_code == 200
    from sqlalchemy import delete

    from app.models import Repository
    async with SessionLocal() as s:
        await s.execute(delete(Repository).where(Repository.id == rid))
        await s.commit()
        assert (await s.execute(select(func.count()).select_from(TaskProgress))).scalar_one() == 0
