"""Issue sync resolves the owning user's OAuth credential at execution time."""
import io
import json
import urllib.error
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from ai_pipeline import github_issues
from app.core.security import encrypt_token
from app.db.session import SessionLocal
from app.main import app
from app.models import Issue, IssueSync, Repository, User
from app.services import issues, jobs
from tests.conftest import FakeQueue, api_client

SAVED = "gho_saved_owner_token"
SHARED = "ghp_shared_server_token"
PASTED = "ghp_explicit_job_token"


@pytest.fixture
def sync_env(db, make_user, auth_settings, monkeypatch):
    auth_settings.github_token = SHARED
    monkeypatch.setattr(issues, "get_settings", lambda: auth_settings)

    async def create(token=SAVED, *, github_id=1, url="https://github.com/acme/private", ownerless=False):
        user, headers = await make_user(github_id=github_id, login=f"user-{github_id}", token=token)
        async with SessionLocal() as session:
            repo = Repository(owner_id=None if ownerless else user.id, url=url, branch="", status="ready")
            session.add(repo)
            await session.commit()
        return user, headers, repo.id

    return create


@pytest.fixture
def fetched_tokens(monkeypatch):
    tokens = []

    def fetch(owner, repo, token, labels, **kwargs):
        assert (owner, repo) == ("acme", "private")
        tokens.append(token)
        return [{"number": 42, "title": "New issue", "labels": [{"name": "good first issue"}]}]

    monkeypatch.setattr(issues, "fetch_issues", fetch)
    return tokens


async def state(repo_id):
    async with SessionLocal() as session:
        sync = await session.get(IssueSync, repo_id)
        rows = (await session.scalars(select(Issue).where(Issue.repo_id == repo_id))).all()
        return sync, [(row.number, row.title, row.body) for row in rows]


async def seed_cache(repo_id):
    await issues._store(repo_id, [github_issues.normalize_issue({"number": 7, "title": "Cached issue"})], None)
    return (await state(repo_id))[0]


async def test_saved_owner_token_wins_over_shared_server_token(sync_env, fetched_tokens, caplog):
    user, _, rid = await sync_env()
    await issues.run_issue_sync(rid)
    assert fetched_tokens == [SAVED]
    sync, rows = await state(rid)
    assert sync.status == "ok" and sync.fetched == 1 and rows[0][0] == 42
    async with SessionLocal() as session:
        stored_user = await session.get(User, user.id)
        assert stored_user.encrypted_access_token != SAVED
        assert SAVED not in stored_user.encrypted_access_token
    for token in (SAVED, SHARED, PASTED):
        assert token not in repr((sync.message, rows)) + caplog.text


async def test_saved_oauth_reaches_github_only_in_authorization_header(sync_env, monkeypatch):
    _, _, rid = await sync_env()
    requests = []

    def respond(request, **kwargs):
        requests.append(request)
        assert request.get_header("Authorization") == f"Bearer {SAVED}"
        assert request.full_url.startswith("https://api.github.com/repos/acme/private/issues?")
        assert SAVED not in request.full_url
        return io.BytesIO(json.dumps([{"number": 42, "title": "Private issue"}]).encode())

    monkeypatch.setattr(github_issues.urllib.request, "urlopen", respond)
    await issues.run_issue_sync(rid)
    sync, rows = await state(rid)
    assert requests and sync.status == "ok" and sync.fetched == 1
    assert rows == [(42, "Private issue", "")]


async def test_explicit_token_wins_even_when_saved_token_cannot_be_decrypted(
    sync_env, fetched_tokens, auth_settings,
):
    _, _, rid = await sync_env()
    auth_settings.token_encryption_key = Fernet.generate_key().decode()
    await issues.run_issue_sync(rid, PASTED)
    assert fetched_tokens == [PASTED]
    assert (await state(rid))[0].status == "ok"


@pytest.mark.parametrize("server_token, expected", [(SHARED, SHARED), ("", None)])
async def test_missing_user_credential_retains_server_or_anonymous_fallback(
    sync_env, fetched_tokens, auth_settings, server_token, expected,
):
    _, _, rid = await sync_env(token=None)
    auth_settings.github_token = server_token
    await issues.run_issue_sync(rid)
    assert fetched_tokens == [expected]
    assert (await state(rid))[0].status == "ok"


async def test_ownerless_legacy_repo_does_not_borrow_another_users_token(sync_env, fetched_tokens):
    _, _, rid = await sync_env(ownerless=True)
    await issues.run_issue_sync(rid)
    assert fetched_tokens == [SHARED]


@pytest.mark.parametrize("broken", ["rotated-key", "missing-key", "corrupt-ciphertext", "empty-credential"])
async def test_unreadable_saved_credential_fails_closed_and_preserves_cache(
    sync_env, fetched_tokens, auth_settings, broken, caplog,
):
    user, _, rid = await sync_env()
    previous = await seed_cache(rid)
    if broken == "rotated-key":
        auth_settings.token_encryption_key = Fernet.generate_key().decode()
    elif broken == "missing-key":
        auth_settings.token_encryption_key = ""
    else:
        async with SessionLocal() as session:
            owner = await session.get(User, user.id)
            owner.encrypted_access_token = encrypt_token("") if broken == "empty-credential" else "not-valid-ciphertext"
            await session.commit()
    await issues.run_issue_sync(rid)
    assert fetched_tokens == []  # Never retry with the shared credential or anonymously.
    sync, rows = await state(rid)
    assert sync.status == "failed" and "Sign in with GitHub again" in sync.message
    assert sync.fetched == previous.fetched and sync.synced_at == previous.synced_at
    assert rows == [(7, "Cached issue", "")]
    assert SAVED not in sync.message + caplog.text


@pytest.mark.parametrize("token", [PASTED, None], ids=["explicit-token", "server-token"])
async def test_non_oauth_auth_failure_is_not_relabelled_as_a_saved_sign_in_failure(
    sync_env, monkeypatch, token,
):
    _, _, rid = await sync_env(token=None)
    selected = []

    def reject(owner, repo, credential, *args, **kwargs):
        selected.append(credential)
        raise github_issues.GitHubError("GitHub rejected the access token (401).", "reauth")

    monkeypatch.setattr(issues, "fetch_issues", reject)
    await issues.run_issue_sync(rid, token)
    assert selected == [token or SHARED]
    sync, _ = await state(rid)
    assert sync.status == "failed" and sync.message == "GitHub rejected the access token (401)."


@pytest.mark.parametrize("status, headers, body, hint", [
    (401, {}, {"message": "Bad credentials"}, "Sign in with GitHub again"),
    (404, {}, {"message": "Not Found"}, "permissions"),
    (403, {}, {"message": "Resource not accessible"}, "OAuth app approval"),
    (403, {"X-RateLimit-Remaining": "0"}, {"message": "Rate limit"}, "rate limit"),
    (429, {}, {"message": "Rate limit"}, "rate limit"),
    (500, {}, {"message": f"An upstream error containing {SAVED}"}, "HTTP 500"),
])
async def test_real_fetcher_auth_errors_are_classified_without_identity_fallback(
    sync_env, monkeypatch, status, headers, body, hint, caplog,
):
    _, _, rid = await sync_env()
    previous = await seed_cache(rid)
    seen = []

    def open_request(request, **kwargs):
        seen.append(request.get_header("Authorization"))
        raise urllib.error.HTTPError(
            request.full_url, status, "failure", headers, io.BytesIO(json.dumps(body).encode()),
        )

    monkeypatch.setattr(github_issues.urllib.request, "urlopen", open_request)
    await issues.run_issue_sync(rid)
    assert seen == [f"Bearer {SAVED}"]
    sync, rows = await state(rid)
    assert sync.status == "failed" and hint in sync.message
    assert sync.fetched == previous.fetched and sync.synced_at == previous.synced_at
    assert rows == [(7, "Cached issue", "")]
    assert SAVED not in sync.message + caplog.text
    assert "pass an access_token" not in sync.message


async def test_network_failure_preserves_cache_and_redacts_selected_token(sync_env, monkeypatch, caplog):
    _, _, rid = await sync_env()
    await seed_cache(rid)

    def unreachable(*args, **kwargs):
        raise urllib.error.URLError(f"Network problem with {SAVED}")

    monkeypatch.setattr(github_issues.urllib.request, "urlopen", unreachable)
    await issues.run_issue_sync(rid)
    sync, rows = await state(rid)
    assert sync.status == "failed" and "Could not reach GitHub" in sync.message
    assert rows == [(7, "Cached issue", "")]
    assert SAVED not in sync.message + caplog.text


async def test_unexpected_fetch_error_does_not_log_or_persist_credential(sync_env, monkeypatch, caplog):
    _, _, rid = await sync_env()
    await seed_cache(rid)

    def crash(*args, **kwargs):
        raise RuntimeError(f"Unexpected failure containing {SAVED}")

    monkeypatch.setattr(issues, "fetch_issues", crash)
    await issues.run_issue_sync(rid)
    sync, rows = await state(rid)
    assert sync.status == "failed" and "Unexpected error" in sync.message
    assert rows == [(7, "Cached issue", "")]
    assert SAVED not in sync.message + caplog.text


async def test_issues_disabled_still_clears_stale_cache(sync_env, monkeypatch):
    _, _, rid = await sync_env()
    await seed_cache(rid)

    def disabled(*args, **kwargs):
        raise github_issues.IssuesDisabled("Issues are turned off for this repository.")

    monkeypatch.setattr(issues, "fetch_issues", disabled)
    await issues.run_issue_sync(rid)
    sync, rows = await state(rid)
    assert sync.status == "ok" and sync.fetched == 0 and rows == []


async def test_manual_sync_queues_no_saved_token_and_uses_latest_owner_credential(
    sync_env, fetched_tokens, monkeypatch,
):
    user, headers, rid = await sync_env()
    queue = FakeQueue()
    monkeypatch.setattr(app.state, "queue", queue, raising=False)
    async with api_client(headers) as client:
        response = await client.post(f"/repos/{rid}/issues/sync")
    assert response.status_code == 202
    assert queue.jobs == [("sync_issues", (rid, None))]
    assert SAVED not in response.text + repr(queue.jobs)
    # A fresh OAuth sign-in before execution must take effect without re-enqueueing.
    async with SessionLocal() as session:
        owner = await session.get(User, user.id)
        owner.encrypted_access_token = encrypt_token("gho_refreshed")
        await session.commit()
    await jobs.sync_issues(*queue.jobs[0][1])
    assert fetched_tokens == ["gho_refreshed"]
    assert (await state(rid))[0].status == "ok"


async def test_same_repo_url_uses_each_owners_token_and_rejects_other_users_sync(
    sync_env, fetched_tokens, monkeypatch,
):
    _, first_headers, first = await sync_env(token="gho_first", github_id=1)
    _, second_headers, second = await sync_env(token="gho_second", github_id=2)
    queue = FakeQueue()
    monkeypatch.setattr(app.state, "queue", queue, raising=False)
    async with api_client(first_headers) as client:
        assert (await client.post(f"/repos/{second}/issues/sync")).status_code == 404
    async with api_client(second_headers) as client:
        assert (await client.post(f"/repos/{first}/issues/sync")).status_code == 404
    assert queue.jobs == []
    await issues.run_issue_sync(first)
    await issues.run_issue_sync(second)
    assert fetched_tokens == ["gho_first", "gho_second"]


async def test_automatic_post_index_sync_resolves_saved_token(sync_env, fetched_tokens, monkeypatch):
    _, _, rid = await sync_env()
    monkeypatch.setattr(jobs, "run_indexing", AsyncMock())
    await jobs.index_repository(rid)
    assert fetched_tokens == [SAVED]
    assert (await state(rid))[0].status == "ok"


async def test_non_github_url_does_not_attempt_token_resolution(sync_env, fetched_tokens, auth_settings):
    _, _, rid = await sync_env(url="/local/repository")
    auth_settings.token_encryption_key = ""
    await issues.run_issue_sync(rid)
    sync, _ = await state(rid)
    assert sync.status == "failed" and "hosted on github.com" in sync.message
    assert fetched_tokens == []


async def test_deleted_repository_does_not_fetch(fetched_tokens, db):
    await issues.run_issue_sync(99999)
    assert fetched_tokens == []
