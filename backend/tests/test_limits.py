"""Abuse protection through the API: per-user rate limits and repository / storage quotas."""
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.db.session import SessionLocal
from app.main import app
from app.models import Chunk, Repository
from app.services.indexing import run_indexing
from app.services.runtime import get_embedder
from tests.test_api import client, index  # noqa: F401  (client is a fixture)
from tests.test_explain import ExplainLLM, use_llm

# ---------------------------------------------------------------------------------------------- rate limits


async def test_search_is_limited_per_user_and_says_when_to_retry(client, git_repo, monkeypatch, make_user):  # noqa: F811
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "rate_limit_read_per_minute", 3)
    limiter.reset()
    for _ in range(3):
        assert (await client.post(f"/repos/{rid}/search", json={"query": "charge card"})).status_code == 200
    r = await client.post(f"/repos/{rid}/search", json={"query": "charge card"})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1 and "Too many" in r.json()["detail"]
    # one user's limit never blocks another user
    _other, headers = await make_user(github_id=2, login="other")
    assert (await client.get("/repos", headers=headers)).status_code == 200


async def test_ask_and_stream_share_the_llm_budget(client, git_repo, monkeypatch):  # noqa: F811
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 2)
    limiter.reset()
    q = {"question": "Where is payment handled?"}
    assert (await client.post(f"/repos/{rid}/ask", json=q)).status_code == 200
    assert (await client.post(f"/repos/{rid}/ask", json=q)).status_code == 200
    assert (await client.post(f"/repos/{rid}/ask", json=q)).status_code == 429
    assert (await client.post(f"/repos/{rid}/ask/stream", json=q)).status_code == 429
    # reading code is a different bucket and still works
    assert (await client.post(f"/repos/{rid}/search", json={"query": "charge card"})).status_code == 200


async def test_explain_refresh_has_its_own_small_budget(client, git_repo, monkeypatch):  # noqa: F811
    rid = await index(client, git_repo)
    use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_refresh_per_hour", 1)
    limiter.reset()
    url = f"/repos/{rid}/explain"
    assert (await client.get(url, params={"file": "shop/payments.py", "refresh": "true"})).status_code == 200
    assert (await client.get(url, params={"file": "shop/payments.py", "refresh": "true"})).status_code == 429
    assert (await client.get(url, params={"file": "shop/payments.py"})).status_code == 200      # plain reads are fine


async def test_llm_options_on_impact_and_tasks_use_the_llm_budget(client, git_repo, monkeypatch):  # noqa: F811
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    limiter.reset()
    ok = await client.get(f"/repos/{rid}/impact", params={"symbol": "shop/payments.py::charge_card", "explain": "true"})
    assert ok.status_code == 200
    again = await client.get(f"/repos/{rid}/impact", params={"symbol": "shop/payments.py::charge_card", "explain": "true"})
    assert again.status_code == 429
    tasks = await client.get(f"/repos/{rid}/onboarding-tasks", params={"explain": "true"})
    assert tasks.status_code == 429
    # without the LLM option the same endpoints are not charged to the LLM budget
    assert (await client.get(f"/repos/{rid}/impact", params={"symbol": "shop/payments.py::charge_card"})).status_code == 200
    assert (await client.get(f"/repos/{rid}/onboarding-tasks")).status_code == 200


async def test_register_and_reindex_are_limited(client, git_repo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "rate_limit_index_per_hour", 2)
    limiter.reset()
    rid = await index(client, git_repo)                                    # hit 1 (register)
    assert (await client.post(f"/repos/{rid}/reindex")).status_code == 202   # hit 2
    r = await client.post(f"/repos/{rid}/reindex")
    assert r.status_code == 429 and "Retry-After" in r.headers


async def test_limits_can_be_turned_off(client, git_repo, monkeypatch):  # noqa: F811
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "rate_limit_read_per_minute", 1)
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    for _ in range(3):
        assert (await client.post(f"/repos/{rid}/search", json={"query": "charge card"})).status_code == 200


async def test_unauthenticated_requests_still_get_401_not_429(client, git_repo):  # noqa: F811
    rid = await index(client, git_repo)
    client.cookies.clear()
    client.headers.pop("Cookie", None)
    assert (await client.post(f"/repos/{rid}/search", json={"query": "charge card"})).status_code == 401


# ---------------------------------------------------------------------------------------------- quotas


async def set_status(rid: int, status: str) -> None:
    async with SessionLocal() as s:
        await s.execute(update(Repository).where(Repository.id == rid).values(status=status))
        await s.commit()


async def chunk_count() -> int:
    async with SessionLocal() as s:
        return (await s.execute(select(func.count()).select_from(Chunk))).scalar_one()


async def test_repository_limit_per_user(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "max_repos_per_user", 2)
    monkeypatch.setattr(get_settings(), "max_active_jobs_per_user", 10)
    ids = []
    for name in ("one", "two"):
        r = await client.post("/repos", json={"url": f"https://github.com/acme/{name}"})
        assert r.status_code == 202
        ids.append(r.json()["id"])
    third = await client.post("/repos", json={"url": "https://github.com/acme/three"})
    assert third.status_code == 403 and "up to 2 repositories" in third.json()["detail"]
    assert len(app.state.queue.jobs) == 2                                    # nothing was queued for the refused one
    again = await client.post("/repos", json={"url": "https://github.com/acme/one"})
    assert again.status_code == 202 and again.json()["id"] == ids[0]         # an existing repo is not a new one
    await set_status(ids[1], "ready")
    assert (await client.delete(f"/repos/{ids[1]}")).status_code == 204      # deleting frees the slot
    assert (await client.post("/repos", json={"url": "https://github.com/acme/three"})).status_code == 202


async def test_repository_limit_is_per_user(client, monkeypatch, make_user):  # noqa: F811
    monkeypatch.setattr(get_settings(), "max_repos_per_user", 1)
    monkeypatch.setattr(get_settings(), "max_active_jobs_per_user", 10)
    assert (await client.post("/repos", json={"url": "https://github.com/acme/one"})).status_code == 202
    assert (await client.post("/repos", json={"url": "https://github.com/acme/two"})).status_code == 403
    _other, headers = await make_user(github_id=2, login="other")
    r = await client.post("/repos", json={"url": "https://github.com/acme/two"}, headers=headers)
    assert r.status_code == 202


async def test_one_user_cannot_fill_the_indexing_queue(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "max_active_jobs_per_user", 1)
    first = await client.post("/repos", json={"url": "https://github.com/acme/one"})
    assert first.status_code == 202
    second = await client.post("/repos", json={"url": "https://github.com/acme/two"})
    assert second.status_code == 429 and "waiting to be indexed" in second.json()["detail"]
    await set_status(first.json()["id"], "ready")                            # the first one finished
    assert (await client.post("/repos", json={"url": "https://github.com/acme/two"})).status_code == 202
    # re-indexing counts as well: "one" is ready but "two" is still queued
    assert (await client.post(f"/repos/{first.json()['id']}/reindex")).status_code == 429


async def test_no_new_repository_when_the_server_storage_is_full(client, git_repo, monkeypatch):  # noqa: F811
    await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "max_total_chunks", await chunk_count())
    r = await client.post("/repos", json={"url": "https://github.com/acme/one"})
    assert r.status_code == 503 and "storage is full" in r.json()["detail"]


async def test_a_repository_that_does_not_fit_fails_before_any_embedding(client, git_repo, monkeypatch):  # noqa: F811
    class NoEmbedding:
        async def aembed_documents(self, texts):
            raise AssertionError("embedding quota must not be spent on a repository that does not fit")

    monkeypatch.setattr(get_settings(), "max_total_chunks", 3)
    r = await client.post("/repos", json={"url": str(git_repo)})
    rid = r.json()["id"]
    await run_indexing(rid, None, llm=None, embedder=NoEmbedding())
    detail = (await client.get(f"/repos/{rid}")).json()
    assert detail["status"] == "failed" and "storage is full" in detail["error"]
    assert await chunk_count() == 0


async def test_reindex_does_not_count_the_repositorys_own_old_chunks(client, git_repo, monkeypatch):  # noqa: F811
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "max_total_chunks", await chunk_count())     # exactly full, by itself
    assert (await client.post(f"/repos/{rid}/reindex")).status_code == 202
    await run_indexing(rid, None, llm=None, embedder=get_embedder())
    assert (await client.get(f"/repos/{rid}")).json()["status"] == "ready"
