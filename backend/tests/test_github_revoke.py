"""Disconnecting GitHub revokes the token at GitHub first; a failed revocation keeps the record so it can be retried."""
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import User
from tests.conftest import api_client


async def stored(user_id: int) -> User:
    async with SessionLocal() as s:
        return (await s.execute(select(User).where(User.id == user_id))).scalar_one()


def revoke_calls(fake_github) -> list:
    return [r for r in fake_github.requests if r.method == "DELETE"]


async def test_disconnect_revokes_the_token_at_github_then_forgets_it(db, make_user, fake_github):
    user, headers = await make_user(token="gho_secret")
    async with api_client(headers) as c:
        out = await c.post("/auth/github/disconnect")
    assert out.status_code == 200 and out.json() == {"ok": True, "github_connected": False}
    assert fake_github.revoked == ["gho_secret"]
    after = await stored(user.id)
    assert after.encrypted_access_token is None and after.token_scopes is None
    (sent,) = revoke_calls(fake_github)
    assert sent.url.path == "/applications/test-client-id/token" and "Basic" in sent.headers["authorization"]


async def test_a_token_that_github_already_considers_gone_still_disconnects(db, make_user, fake_github):
    fake_github.revoke_status = 404
    user, headers = await make_user(token="gho_old")
    async with api_client(headers) as c:
        assert (await c.post("/auth/github/disconnect")).status_code == 200
    assert (await stored(user.id)).encrypted_access_token is None


async def test_failed_revocation_keeps_the_token_and_can_be_retried(db, make_user, fake_github):
    fake_github.revoke_status = 500
    user, headers = await make_user(token="gho_secret")
    async with api_client(headers) as c:
        out = await c.post("/auth/github/disconnect")
        assert out.status_code == 502 and "try again" in out.json()["detail"]
        assert "gho_secret" not in out.text
        assert (await stored(user.id)).encrypted_access_token is not None         # not pretending it worked
        fake_github.revoke_status = 204                                           # GitHub recovers; the user retries
        assert (await c.post("/auth/github/disconnect")).status_code == 200
    assert fake_github.revoked == ["gho_secret"]
    assert (await stored(user.id)).encrypted_access_token is None


async def test_rejected_app_credentials_keep_the_token(db, make_user, fake_github, auth_settings):
    user, headers = await make_user(token="gho_secret")
    auth_settings.github_client_secret = "wrong-secret"                           # GitHub answers 401 to the revocation
    async with api_client(headers) as c:
        assert (await c.post("/auth/github/disconnect")).status_code == 502
    assert fake_github.revoked == [] and (await stored(user.id)).encrypted_access_token is not None


async def test_rate_limited_revocation_keeps_the_token(db, make_user, fake_github):
    fake_github.revoke_status = 429
    user, headers = await make_user(token="gho_secret")
    async with api_client(headers) as c:
        out = await c.post("/auth/github/disconnect")
    assert out.status_code == 502 and "rate limit" in out.json()["detail"].lower()
    assert (await stored(user.id)).encrypted_access_token is not None


async def test_disconnect_without_a_saved_token_does_not_call_github(db, make_user, fake_github):
    _, headers = await make_user()
    async with api_client(headers) as c:
        out = await c.post("/auth/github/disconnect")
    assert out.status_code == 200 and out.json() == {"ok": True, "github_connected": False}
    assert revoke_calls(fake_github) == []


async def test_an_unreadable_token_is_removed_with_a_warning(db, make_user, fake_github, auth_settings):
    user, headers = await make_user(token="gho_secret")
    auth_settings.token_encryption_key = Fernet.generate_key().decode()           # the old key is gone: cannot decrypt
    async with api_client(headers) as c:
        out = await c.post("/auth/github/disconnect")
    assert out.status_code == 200 and "not revoked" in out.json()["warning"]
    assert revoke_calls(fake_github) == [] and (await stored(user.id)).encrypted_access_token is None


async def test_missing_app_credentials_remove_the_token_with_a_warning(db, make_user, fake_github, auth_settings):
    user, headers = await make_user(token="gho_secret")
    auth_settings.github_client_secret = ""
    async with api_client(headers) as c:
        out = await c.post("/auth/github/disconnect")
    assert out.status_code == 200 and "not revoked" in out.json()["warning"]
    assert revoke_calls(fake_github) == [] and (await stored(user.id)).encrypted_access_token is None


async def test_disconnect_keeps_the_app_session_active(db, make_user, fake_github):
    _, headers = await make_user(token="gho_secret")
    async with api_client(headers) as c:
        assert (await c.post("/auth/github/disconnect")).status_code == 200
        me = await c.get("/auth/me")
    assert me.status_code == 200 and me.json()["github_connected"] is False


async def test_disconnect_needs_a_session(db, fake_github):
    async with api_client() as c:
        assert (await c.post("/auth/github/disconnect")).status_code == 401
    assert revoke_calls(fake_github) == []
