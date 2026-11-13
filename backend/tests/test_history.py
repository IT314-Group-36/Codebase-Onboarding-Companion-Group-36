"""GET /repos/{id}/history: commits + contributor shares fetched from GitHub on demand."""
import pytest

from app.db.session import SessionLocal
from app.models import Repository
from tests.conftest import api_client


def _commit(sha, message, login=None, name="Someone", date="2026-11-01T10:00:00Z"):
    return {"sha": sha * 40, "html_url": f"https://github.com/o/r/commit/{sha}",
            "author": {"login": login, "avatar_url": f"https://av/{login}"} if login else None,
            "commit": {"message": message, "author": {"name": name, "date": date}}}


async def _ready_repo(user, url="https://github.com/o/r", branch="main", status="ready"):
    async with SessionLocal() as s:
        r = Repository(owner_id=user.id, url=url, branch=branch, status=status)
        s.add(r)
        await s.commit()
        return r.id


async def test_history_returns_commits_and_contributor_shares(db, make_user, fake_github):
    user, headers = await make_user(token="gho_testtoken")
    fake_github.commits = [_commit("a", "Fix bug\n\nlong body", "octo", "Octo"),
                           _commit("b", "Add feature", "octo", "Octo"),
                           _commit("c", "", None, "Anon"),
                           _commit("d", "Docs", "zed", "Zed")]
    rid = await _ready_repo(user)
    async with api_client(headers) as c:
        r = await c.get(f"/repos/{rid}/history?path=src/app.py&limit=20")
    assert r.status_code == 200
    body = r.json()
    assert body["repository"] == "o/r" and body["branch"] == "main" and body["path"] == "src/app.py"
    assert body["sample_size"] == 4
    assert body["commits"][0]["message"] == "Fix bug" and body["commits"][0]["short_sha"] == "aaaaaaa"
    assert body["commits"][2]["message"] == "(no commit message)"
    top = body["contributors"][0]
    assert top["login"] == "octo" and top["commits"] == 2 and top["share"] == 50.0
    assert {p["name"] for p in body["contributors"]} == {"Octo", "Anon", "Zed"}
    sent = fake_github.requests[-1].url.params
    assert sent["sha"] == "main" and sent["path"] == "src/app.py" and sent["per_page"] == "20"


async def test_empty_repository_gives_empty_history_not_an_error(db, make_user, fake_github):
    user, headers = await make_user(token="gho_testtoken")
    fake_github.commits_empty = True
    rid = await _ready_repo(user)
    async with api_client(headers) as c:
        r = await c.get(f"/repos/{rid}/history")
    assert r.status_code == 200
    assert r.json()["commits"] == [] and r.json()["contributors"] == [] and r.json()["sample_size"] == 0


async def test_revoked_token_uses_the_reauth_error_shape_of_the_github_routes(db, make_user, fake_github):
    user, headers = await make_user(token="gho_revoked")             # FakeGitHub only accepts gho_testtoken
    rid = await _ready_repo(user)
    async with api_client(headers) as c:
        r = await c.get(f"/repos/{rid}/history")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "github_reauth_required"


async def test_user_without_saved_token_must_sign_in_again(db, make_user, fake_github):
    user, headers = await make_user()                                # no saved token
    rid = await _ready_repo(user)
    async with api_client(headers) as c:
        r = await c.get(f"/repos/{rid}/history")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "github_reauth_required"


async def test_rate_limit_and_server_errors_are_mapped(db, make_user, fake_github):
    user, headers = await make_user(token="gho_testtoken")
    rid = await _ready_repo(user)
    async with api_client(headers) as c:
        fake_github.force_status = 429
        assert (await c.get(f"/repos/{rid}/history")).status_code == 429
        fake_github.force_status = 500
        assert (await c.get(f"/repos/{rid}/history")).status_code == 502


async def test_non_github_repo_is_rejected(db, make_user, fake_github, tmp_path):
    user, headers = await make_user(token="gho_testtoken")
    rid = await _ready_repo(user, url=str(tmp_path))
    async with api_client(headers) as c:
        assert (await c.get(f"/repos/{rid}/history")).status_code == 422


async def test_history_requires_login_ownership_and_a_ready_repo(db, make_user, fake_github):
    owner, _ = await make_user(github_id=1, login="owner", token="gho_testtoken")
    _, other_headers = await make_user(github_id=2, login="other", token="gho_testtoken")
    rid = await _ready_repo(owner)
    async with api_client() as c:
        assert (await c.get(f"/repos/{rid}/history")).status_code == 401
    async with api_client(other_headers) as c:
        assert (await c.get(f"/repos/{rid}/history")).status_code == 404       # someone else's repo
    pending = await _ready_repo(owner, branch="dev", status="indexing")
    from app.core.security import create_session_token
    async with api_client({"Cookie": f"session={create_session_token(owner.id)}"}) as c:
        assert (await c.get(f"/repos/{pending}/history")).status_code == 409


@pytest.mark.parametrize("limit", [0, 101])
async def test_limit_is_bounded(db, make_user, fake_github, limit):
    user, headers = await make_user(token="gho_testtoken")
    rid = await _ready_repo(user)
    async with api_client(headers) as c:
        assert (await c.get(f"/repos/{rid}/history?limit={limit}")).status_code == 422
