"""Private repositories: the saved GitHub token is used to clone, and the GitHub repo/branch lists."""
import httpx
import pytest
from cryptography.fernet import Fernet

from ai_pipeline import repo as repo_module
from app.db.session import SessionLocal
from app.main import app
from app.models import Repository
from app.services import indexing
from app.services.indexing import run_indexing
from app.services.runtime import get_embedder
from tests.conftest import FakeQueue, api_client
from tests.test_api import FakeLLM

NEEDS_LOGIN = "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
CLONE_HEAD = "Could not clone the repo. Is it public (or is the token valid), and are the URL/branch correct?\n"


class CloneCalls(list):
    """The tokens clone_repo was called with, in order (None = anonymous)."""
    install = None


@pytest.fixture
def clone_calls(monkeypatch):
    """Replaces the network part of cloning. `behaviour(token)` returns None (succeed) or an error text (fail).
    The default behaviour is a private repo: it only succeeds when given the saved token."""
    real = repo_module.clone_repo
    calls = CloneCalls()

    def install(behaviour=lambda token: None if token == "gho_stored" else NEEDS_LOGIN):
        def fake(url, branch, dest, token=None, timeout=300):
            calls.append(token)
            err = behaviour(token)
            if err:
                raise RuntimeError(CLONE_HEAD + err)
            return real(url, branch, dest, None)               # the test repo is a local directory
        monkeypatch.setattr(indexing, "clone_repo", fake)
        return calls
    calls.install = install
    return calls


async def register_and_index(headers, git_repo, pasted=None):
    app.state.queue = FakeQueue()
    async with api_client(headers) as c:
        rid = (await c.post("/repos", json={"url": str(git_repo), "access_token": pasted})).json()["id"]
        jobs = list(app.state.queue.jobs)
    await run_indexing(rid, pasted, llm=FakeLLM(), embedder=get_embedder())
    async with SessionLocal() as s:
        return await s.get(Repository, rid), jobs


# ---------- cloning with the saved token ----------

async def test_private_repo_is_cloned_with_the_saved_token_and_token_never_enters_the_queue(db, make_user, git_repo, clone_calls):
    clone_calls.install()
    _, headers = await make_user(token="gho_stored")
    repo, jobs = await register_and_index(headers, git_repo)
    assert repo.status == "ready"
    assert clone_calls == [None, "gho_stored"]                  # anonymous first, then the saved token
    assert jobs == [("index_repository", (repo.id, None))] and "gho_stored" not in repr(jobs)


async def test_public_repo_never_touches_the_saved_token(db, make_user, git_repo, clone_calls):
    clone_calls.install(lambda token: None)
    _, headers = await make_user(token="gho_stored")
    repo, _ = await register_and_index(headers, git_repo)
    assert repo.status == "ready" and clone_calls == [None]


async def test_a_pasted_token_wins_and_the_saved_one_is_left_alone(db, make_user, git_repo, clone_calls):
    clone_calls.install(lambda token: None if token == "gho_pasted" else NEEDS_LOGIN)
    _, headers = await make_user(token="gho_stored")
    repo, jobs = await register_and_index(headers, git_repo, pasted="gho_pasted")
    assert repo.status == "ready" and clone_calls == ["gho_pasted"]
    assert jobs == [("index_repository", (repo.id, "gho_pasted"))]          # unchanged behaviour for pasted tokens


async def test_revoked_saved_token_gives_a_sign_in_again_message(db, make_user, git_repo, clone_calls):
    clone_calls.install(lambda token: "fatal: Authentication failed for 'https://github.com/o/r/'" if token else NEEDS_LOGIN)
    _, headers = await make_user(token="gho_stored")
    repo, _ = await register_and_index(headers, git_repo)
    assert repo.status == "failed" and "Sign in with GitHub again" in repo.error and "gho_stored" not in repo.error


async def test_no_access_gives_a_private_repo_hint(db, make_user, git_repo, clone_calls):
    clone_calls.install(lambda token: "remote: Repository not found.")
    _, headers = await make_user(token="gho_stored")
    repo, _ = await register_and_index(headers, git_repo)
    assert repo.status == "failed" and "your GitHub account" in repo.error and "organization" in repo.error
    assert "Repository not found" in repo.error                 # the real git message is kept for debugging


async def test_wrong_branch_is_not_retried_with_the_token(db, make_user, git_repo, clone_calls):
    clone_calls.install(lambda token: "fatal: Remote branch nope not found in upstream origin")
    _, headers = await make_user(token="gho_stored")
    repo, _ = await register_and_index(headers, git_repo)
    assert repo.status == "failed" and "Remote branch nope" in repo.error and clone_calls == [None]


async def test_user_without_a_saved_token_fails_after_one_attempt(db, make_user, git_repo, clone_calls):
    clone_calls.install()
    _, headers = await make_user()                              # no token
    repo, _ = await register_and_index(headers, git_repo)
    assert repo.status == "failed" and "Could not clone" in repo.error and clone_calls == [None]


async def test_unreadable_saved_token_asks_to_sign_in_again(db, make_user, git_repo, clone_calls, auth_settings):
    clone_calls.install()
    _, headers = await make_user(token="gho_stored")
    auth_settings.token_encryption_key = Fernet.generate_key().decode()      # the key changed after the token was saved
    repo, _ = await register_and_index(headers, git_repo)
    assert repo.status == "failed" and "Sign in with GitHub again" in repo.error and clone_calls == [None]


# ---------- GitHub repo and branch lists ----------

async def test_lists_the_users_github_repos_with_the_saved_token(db, make_user, fake_github):
    fake_github.repos = ["me/app", "me/secret-private", "acme/tool", "acme/docs"]
    _, headers = await make_user(token="gho_testtoken")
    async with api_client(headers) as c:
        first = (await c.get("/github/repos", params={"per_page": 3})).json()
        assert [r["full_name"] for r in first["repos"]] == ["me/app", "me/secret-private", "acme/tool"]
        assert first["has_more"] is True and first["page"] == 1
        assert first["repos"][1]["private"] is True and first["repos"][0]["url"] == "https://github.com/me/app"
        assert set(first["repos"][0]) == {"full_name", "url", "private", "default_branch", "description", "language", "updated_at", "owner"}
        second = (await c.get("/github/repos", params={"per_page": 3, "page": 2})).json()
        assert [r["full_name"] for r in second["repos"]] == ["acme/docs"] and second["has_more"] is False
        found = (await c.get("/github/repos", params={"q": "ACME"})).json()
        assert [r["full_name"] for r in found["repos"]] == ["acme/tool", "acme/docs"]
    assert fake_github.requests[-1].headers["authorization"] == "Bearer gho_testtoken"


async def test_repo_list_errors_are_clear(db, make_user, fake_github):
    _, headers = await make_user(token="gho_testtoken")
    async with api_client(headers) as c:
        fake_github.valid_token = "gho_other"                                    # GitHub now rejects the saved token
        r = await c.get("/github/repos")
        assert r.status_code == 403 and r.json()["detail"]["code"] == "github_reauth_required"
        fake_github.valid_token, fake_github.force_status = "gho_testtoken", 403
        assert (await c.get("/github/repos")).status_code == 429
        fake_github.force_status = 500
        assert (await c.get("/github/repos")).status_code == 502
    _, nokey_headers = await make_user(2, "no-token")
    async with api_client(nokey_headers) as c:                                  # signed in, but no GitHub token saved
        r = await c.get("/github/repos")
        assert r.status_code == 403 and r.json()["detail"]["code"] == "github_reauth_required"


async def test_branches_returns_default_first_class_and_names(db, make_user, fake_github):
    fake_github.branches = {"me/app": ["main", "develop", "release/1.0"]}
    fake_github.default_branch = "develop"
    _, headers = await make_user(token="gho_testtoken")
    async with api_client(headers) as c:
        r = await c.get("/github/branches", params={"repo": "me/app"})
        assert r.json() == {"default_branch": "develop", "branches": ["main", "develop", "release/1.0"], "truncated": False}
        assert (await c.get("/github/branches", params={"repo": "me/missing"})).status_code == 404
        for bad in ("noslash", "a b/c", "../etc/passwd", "a/b/c", ""):
            assert (await c.get("/github/branches", params={"repo": bad})).status_code == 422, bad


async def test_github_calls_use_no_other_hosts(db, make_user, fake_github):
    fake_github.repos = ["me/app"]
    _, headers = await make_user(token="gho_testtoken")
    async with api_client(headers) as c:
        await c.get("/github/repos")
    assert {r.url.host for r in fake_github.requests} == {"api.github.com"}
    assert all(isinstance(r, httpx.Request) for r in fake_github.requests)
