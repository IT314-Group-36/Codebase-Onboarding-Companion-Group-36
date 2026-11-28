"""Server-side logout: logout and "log out everywhere" cut off every copy of the session cookie."""
from urllib.parse import parse_qs, urlparse

from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import select

from app.core import security
from app.db.session import SessionLocal
from app.models import User
from tests.conftest import api_client


def cookie(user_id: int, version: int = 0) -> dict:
    return {"Cookie": f"session={security.create_session_token(user_id, version)}"}


async def stored_version(user_id: int) -> int:
    async with SessionLocal() as s:
        return (await s.execute(select(User.session_version).where(User.id == user_id))).scalar_one()


async def sign_in(client):
    """Run the whole login flow against the fake GitHub; the session cookie lands in the client's cookie jar."""
    start = await client.get("/auth/github/login")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return await client.get("/auth/github/callback", params={"code": "abc", "state": state})


# ---------- the cookie format (no database) ----------

def test_session_cookie_carries_the_version(auth_settings):
    token = security.create_session_token(5, 3)
    assert security.read_session(token) == (5, 3)
    assert security.read_session_token(token) == 5


def test_cookie_issued_before_sessions_had_a_version_counts_as_version_zero(auth_settings):
    legacy = URLSafeTimedSerializer(auth_settings.session_secret, salt="session").dumps({"uid": 7})
    assert security.read_session(legacy) == (7, 0)
    assert security.read_session(security.create_session_token(7)) == (7, 0)


def test_a_malformed_version_is_rejected(auth_settings):
    signer = URLSafeTimedSerializer(auth_settings.session_secret, salt="session")
    for bad in ("1", None, True, 1.5, [1]):
        assert security.read_session(signer.dumps({"uid": 7, "ver": bad})) is None
    assert security.read_session(signer.dumps([7, 0])) is None
    assert security.read_session("garbage") is None


# ---------- logout ----------

async def test_new_users_start_at_session_version_zero(db, make_user):
    user, _ = await make_user()
    assert await stored_version(user.id) == 0


async def test_logout_cuts_off_a_copied_cookie(db, make_user):
    user, headers = await make_user()
    async with api_client(headers) as mine, api_client(headers) as stolen:        # `stolen` holds a copy of the cookie
        assert (await mine.get("/auth/me")).status_code == 200
        assert (await stolen.get("/auth/me")).status_code == 200
        out = await mine.post("/auth/logout")
        assert out.status_code == 200 and "Max-Age=0" in out.headers["set-cookie"]
        assert (await stolen.get("/auth/me")).status_code == 401                  # the copy is dead too
    assert await stored_version(user.id) == 1


async def test_logout_without_a_session_is_harmless(db, make_user):
    user, _ = await make_user()
    async with api_client() as anon, api_client({"Cookie": "session=garbage"}) as forged:
        for client in (anon, forged):
            out = await client.post("/auth/logout")
            assert out.status_code == 200 and "Max-Age=0" in out.headers["set-cookie"]
    assert await stored_version(user.id) == 0                                     # nobody else was logged out


async def test_logout_everywhere_needs_a_session_and_ends_every_session(db, fake_github):
    async with api_client() as anon:
        assert (await anon.post("/auth/logout-all")).status_code == 401
    async with api_client() as laptop, api_client() as phone:
        await sign_in(laptop)
        await sign_in(phone)
        assert (await laptop.get("/auth/me")).status_code == 200
        assert (await phone.get("/auth/me")).status_code == 200
        out = await phone.post("/auth/logout-all")
        assert out.status_code == 200 and "Max-Age=0" in out.headers["set-cookie"]
        assert (await laptop.get("/auth/me")).status_code == 401
        assert (await phone.get("/auth/me")).status_code == 401


async def test_a_new_login_after_logout_works_and_the_old_cookie_stays_dead(db, fake_github):
    async with api_client() as first:
        await sign_in(first)
        old_cookie = first.cookies["session"]
        assert (await first.post("/auth/logout")).status_code == 200
        assert (await first.get("/auth/me")).status_code == 401
        assert (await sign_in(first)).status_code == 302
        assert (await first.get("/auth/me")).status_code == 200                   # signed in again, new version
        async with api_client({"Cookie": f"session={old_cookie}"}) as old:
            assert (await old.get("/auth/me")).status_code == 401


# ---------- the upgrade ----------

async def test_cookie_issued_before_the_upgrade_still_works(db, make_user, auth_settings):
    user, _ = await make_user()
    legacy = URLSafeTimedSerializer(auth_settings.session_secret, salt="session").dumps({"uid": user.id})
    async with api_client({"Cookie": f"session={legacy}"}) as client:
        assert (await client.get("/auth/me")).status_code == 200


async def test_a_cookie_with_the_wrong_version_is_rejected(db, make_user):
    user, _ = await make_user()
    for version in (1, 5, -1):
        async with api_client(cookie(user.id, version)) as client:
            assert (await client.get("/auth/me")).status_code == 401
    async with api_client(cookie(user.id, 0)) as client:
        assert (await client.get("/auth/me")).status_code == 200
