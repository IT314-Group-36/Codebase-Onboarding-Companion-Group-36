"""GitHub OAuth login, the session, and per-user access to repositories."""
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select

from app.core import security
from app.db.session import SessionLocal
from app.main import app
from app.models import User
from tests.conftest import FakeQueue, api_client


@pytest.fixture
async def anon(db, fake_github):
    app.state.queue = FakeQueue()
    async with api_client() as c:
        yield c


async def sign_in(client):
    """Run the whole login flow against the fake GitHub. Returns the callback response."""
    start = await client.get("/auth/github/login")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return await client.get("/auth/github/callback", params={"code": "abc", "state": state})


async def user_count() -> int:
    async with SessionLocal() as s:
        return (await s.execute(select(func.count()).select_from(User))).scalar_one()


# ---------- configuration ----------

async def test_config_reports_whether_login_is_available(anon, auth_settings):
    assert (await anon.get("/auth/config")).json() == {"github_login_enabled": True}
    auth_settings.github_client_id = ""
    assert (await anon.get("/auth/config")).json() == {"github_login_enabled": False}
    auth_settings.github_client_id, auth_settings.token_encryption_key = "id", "not-a-key"
    assert (await anon.get("/auth/config")).json() == {"github_login_enabled": False}


async def test_login_when_not_configured_goes_back_to_the_frontend_with_an_error(anon, auth_settings):
    auth_settings.github_client_secret = ""
    r = await anon.get("/auth/github/login")
    assert r.status_code == 302 and r.headers["location"].startswith("http://localhost:5173/auth/callback?error=not_configured")


# ---------- the login flow ----------

async def test_login_redirects_to_github_with_state_cookie(anon, auth_settings):
    r = await anon.get("/auth/github/login")
    assert r.status_code == 302
    u = urlparse(r.headers["location"])
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert (u.netloc, u.path) == ("github.com", "/login/oauth/authorize")
    assert q["client_id"] == "test-client-id" and q["scope"] == "repo read:user"
    assert q["redirect_uri"] == "http://localhost:5173/api/auth/github/callback"
    cookie = r.headers["set-cookie"]
    assert f"oauth_state={q['state']}" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie and "Secure" not in cookie
    auth_settings.cookie_secure = True
    assert "Secure" in (await anon.get("/auth/github/login")).headers["set-cookie"]


async def test_successful_login_creates_user_stores_encrypted_token_and_sets_session(anon, fake_github):
    r = await sign_in(anon)
    assert r.status_code == 302 and r.headers["location"] == "http://localhost:5173/auth/callback"
    session_cookie = next(c for c in r.headers.get_list("set-cookie") if c.startswith("session="))
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie and "Path=/" in session_cookie
    sent = next(x for x in fake_github.requests if x.url.path == "/login/oauth/access_token")
    assert b'"code":"abc"' in sent.content.replace(b" ", b"") and b"test-client-secret" in sent.content

    async with SessionLocal() as s:
        u = (await s.execute(select(User))).scalar_one()
    assert (u.github_id, u.login, u.name, u.token_scopes) == (4242, "octo", "Octo Cat", "repo,read:user")
    assert "gho_testtoken" not in u.encrypted_access_token and security.decrypt_token(u.encrypted_access_token) == "gho_testtoken"

    me = await anon.get("/auth/me")                                  # the cookie jar now holds the session
    assert me.status_code == 200
    assert me.json()["login"] == "octo" and me.json()["github_connected"] is True
    assert "gho_testtoken" not in me.text and "encrypted" not in me.text


async def test_signing_in_again_updates_the_same_user_and_token(anon, fake_github):
    await sign_in(anon)
    fake_github.token_response = {"access_token": "gho_second", "scope": "repo"}
    fake_github.valid_token = "gho_second"
    fake_github.user = {**fake_github.user, "login": "octo-renamed"}
    await sign_in(anon)
    assert await user_count() == 1
    async with SessionLocal() as s:
        u = (await s.execute(select(User))).scalar_one()
    assert u.login == "octo-renamed" and security.decrypt_token(u.encrypted_access_token) == "gho_second"


async def test_callback_rejects_missing_or_wrong_state(anon):
    start = await anon.get("/auth/github/login")
    good_state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    wrong = await anon.get("/auth/github/callback", params={"code": "abc", "state": "forged"})
    assert "error=invalid_state" in wrong.headers["location"]
    async with api_client() as fresh:                                 # no state cookie at all (login started elsewhere)
        nocookie = await fresh.get("/auth/github/callback", params={"code": "abc", "state": good_state})
    assert "error=invalid_state" in nocookie.headers["location"]
    assert await user_count() == 0
    assert not any(c.startswith("session=") for c in wrong.headers.get_list("set-cookie") + nocookie.headers.get_list("set-cookie"))


async def test_callback_handles_cancel_and_github_errors_without_reflecting_input(anon, fake_github):
    start = await anon.get("/auth/github/login")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    denied = await anon.get("/auth/github/callback", params={"error": "access_denied", "state": state})
    assert "error=access_denied" in denied.headers["location"]
    evil = await anon.get("/auth/github/callback", params={"error": "<b>evil</b>", "error_description": "evil text"})
    assert "error=github_error" in evil.headers["location"] and "evil" not in evil.headers["location"]

    fake_github.token_response = {"error": "bad_verification_code"}
    bad_code = await sign_in(anon)
    assert "error=github_error" in bad_code.headers["location"]
    assert await user_count() == 0


async def test_callback_survives_a_misconfigured_encryption_key(anon, auth_settings):
    start = await anon.get("/auth/github/login")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    auth_settings.token_encryption_key = "broken"
    r = await anon.get("/auth/github/callback", params={"code": "abc", "state": state})
    assert r.status_code == 302 and "error=" in r.headers["location"]
    assert await user_count() == 0


# ---------- session ----------

async def test_me_needs_a_session_and_logout_clears_the_cookie(anon):
    assert (await anon.get("/auth/me")).status_code == 401
    await sign_in(anon)
    assert (await anon.get("/auth/me")).status_code == 200
    out = await anon.post("/auth/logout")
    assert out.status_code == 200 and "Max-Age=0" in out.headers["set-cookie"]
    assert (await anon.get("/auth/me")).status_code == 401


# ---------- every repo route needs a session, and users only see their own repos ----------

async def test_repo_routes_require_sign_in(anon, git_repo):
    for method, path in (("get", "/repos"), ("post", "/repos"), ("get", "/repos/1"), ("post", "/repos/1/reindex"),
                         ("get", "/repos/1/map"), ("get", "/repos/1/files"), ("get", "/repos/1/files/a.py"),
                         ("get", "/repos/1/symbols"), ("post", "/repos/1/search"), ("post", "/repos/1/ask"),
                         ("get", "/repos/1/impact"), ("get", "/github/repos"), ("get", "/github/branches")):
        r = await getattr(anon, method)(path, **({"json": {"url": str(git_repo)}} if method == "post" and path == "/repos" else {}))
        assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"


async def test_users_cannot_see_or_touch_each_others_repos(db, make_user, git_repo):
    app.state.queue = FakeQueue()
    (_, a_headers), (_, b_headers) = await make_user(1, "alice"), await make_user(2, "bob")
    async with api_client(a_headers) as a, api_client(b_headers) as b:
        mine = (await a.post("/repos", json={"url": str(git_repo)})).json()["id"]
        assert [r["id"] for r in (await a.get("/repos")).json()] == [mine]
        assert (await b.get("/repos")).json() == []
        for method, path in (("get", f"/repos/{mine}"), ("post", f"/repos/{mine}/reindex"), ("get", f"/repos/{mine}/map"),
                             ("get", f"/repos/{mine}/files"), ("post", f"/repos/{mine}/search"), ("post", f"/repos/{mine}/ask"),
                             ("get", f"/repos/{mine}/impact")):
            r = await getattr(b, method)(path, **({"json": {"query": "x", "question": "x"}} if method == "post" else {}))
            assert r.status_code == 404, f"{method.upper()} {path} -> {r.status_code}"
        theirs = (await b.post("/repos", json={"url": str(git_repo)})).json()["id"]      # same repo, separate copy
        assert theirs != mine
        assert [r["id"] for r in (await b.get("/repos")).json()] == [theirs]
        assert len(app.state.queue.jobs) == 2
