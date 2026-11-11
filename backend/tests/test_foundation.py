"""Auth foundation: token encryption, session cookies, users/ownership schema, auth dependencies.

The first block needs no database. The rest uses the real Postgres schema from the Alembic migrations."""
import httpx
import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI
from sqlalchemy.exc import IntegrityError

from app.api import deps
from app.core import security
from app.core.config import Settings
from app.db.session import SessionLocal, engine
from app.models import Repository, User
from app.schemas import UserOut

SECRET = "s" * 48


def use_settings(monkeypatch, **overrides) -> Settings:
    """Point the security and deps modules at a Settings object with the given overrides."""
    cfg = Settings(_env_file=None, **overrides)
    monkeypatch.setattr(security, "get_settings", lambda: cfg)
    monkeypatch.setattr(deps, "get_settings", lambda: cfg)
    return cfg


# ---------- token encryption (no DB) ----------

def test_token_roundtrip_and_ciphertext_hides_plaintext(monkeypatch):
    use_settings(monkeypatch, token_encryption_key=Fernet.generate_key().decode())
    cipher = security.encrypt_token("gho_secretvalue123")
    assert "gho_secretvalue123" not in cipher
    assert security.decrypt_token(cipher) == "gho_secretvalue123"


def test_encryption_needs_a_valid_key(monkeypatch):
    use_settings(monkeypatch, token_encryption_key="")
    with pytest.raises(security.SecurityConfigError, match="not set"):
        security.encrypt_token("x")
    use_settings(monkeypatch, token_encryption_key="not-a-fernet-key")
    with pytest.raises(security.SecurityConfigError, match="valid Fernet key"):
        security.encrypt_token("x")


def test_key_rotation_keeps_old_tokens_readable(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    use_settings(monkeypatch, token_encryption_key=old)
    cipher = security.encrypt_token("tok")
    use_settings(monkeypatch, token_encryption_key=f"{new},{old}")          # new key first, old kept for reading
    assert security.decrypt_token(cipher) == "tok"
    rotated = security.rotate_token(cipher)
    use_settings(monkeypatch, token_encryption_key=new)                    # old key removed
    assert security.decrypt_token(rotated) == "tok"
    with pytest.raises(security.TokenDecryptError):
        security.decrypt_token(cipher)


def test_tampered_or_foreign_ciphertext_is_rejected(monkeypatch):
    use_settings(monkeypatch, token_encryption_key=Fernet.generate_key().decode())
    cipher = security.encrypt_token("tok")
    with pytest.raises(security.TokenDecryptError):
        security.decrypt_token(cipher[:-4] + "AAAA")
    with pytest.raises(security.TokenDecryptError):
        security.decrypt_token("garbage")


# ---------- session cookie (no DB) ----------

def test_session_roundtrip(monkeypatch):
    use_settings(monkeypatch, session_secret=SECRET)
    assert security.read_session_token(security.create_session_token(42)) == 42


def test_session_rejects_tampering_wrong_secret_and_garbage(monkeypatch):
    use_settings(monkeypatch, session_secret=SECRET)
    token = security.create_session_token(7)
    assert security.read_session_token(token + "x") is None
    assert security.read_session_token("garbage") is None
    use_settings(monkeypatch, session_secret="t" * 48)
    assert security.read_session_token(token) is None


def test_session_expires(monkeypatch):
    use_settings(monkeypatch, session_secret=SECRET, session_ttl_seconds=-1)   # already older than the allowed age
    assert security.read_session_token(security.create_session_token(7)) is None


def test_session_needs_a_long_secret(monkeypatch):
    use_settings(monkeypatch, session_secret="short")
    with pytest.raises(security.SecurityConfigError, match="at least 32"):
        security.create_session_token(1)


def test_oauth_configured_flag():
    assert not Settings(_env_file=None, github_client_id="a").github_oauth_configured
    assert Settings(_env_file=None, github_client_id="a", github_client_secret="b",
                    session_secret=SECRET, token_encryption_key="k").github_oauth_configured


def test_user_schema_never_exposes_token_fields():
    assert set(UserOut.model_fields) == {"id", "github_id", "login", "name", "email", "avatar_url"}


# ---------- schema and ownership rules (real Postgres) ----------

async def add_user(session, github_id: int, login: str) -> User:
    u = User(github_id=github_id, login=login)
    session.add(u)
    await session.commit()
    return u


async def test_migration_created_users_and_owner_column(db):
    async with engine.connect() as conn:
        def inspect(sync_conn):
            insp = sa.inspect(sync_conn)
            return ({c["name"] for c in insp.get_columns("users")}, {c["name"] for c in insp.get_columns("repositories")},
                    {i["name"] for i in insp.get_indexes("repositories")})
        user_cols, repo_cols, repo_idx = await conn.run_sync(inspect)
    assert {"github_id", "login", "encrypted_access_token", "token_scopes"} <= user_cols
    assert "owner_id" in repo_cols
    assert {"ix_repositories_owner_id", "uq_repositories_unowned_url_branch"} <= repo_idx


async def test_github_id_is_unique(db):
    async with SessionLocal() as s:
        await add_user(s, 1, "a")
        s.add(User(github_id=1, login="b"))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_two_users_can_index_the_same_repo_but_not_twice(db):
    async with SessionLocal() as s:
        a, b = await add_user(s, 1, "a"), await add_user(s, 2, "b")
        url = "https://github.com/o/r"
        s.add_all([Repository(url=url, branch="", owner_id=a.id), Repository(url=url, branch="", owner_id=b.id)])
        await s.commit()
        s.add(Repository(url=url, branch="", owner_id=a.id))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_unowned_repos_keep_the_old_url_branch_rule(db):
    async with SessionLocal() as s:
        s.add(Repository(url="https://github.com/o/r", branch=""))
        await s.commit()
        s.add(Repository(url="https://github.com/o/r", branch=""))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_deleting_a_user_deletes_their_repos(db):
    async with SessionLocal() as s:
        u = await add_user(s, 1, "a")
        s.add(Repository(url="https://github.com/o/r", branch="", owner_id=u.id))
        await s.commit()
        await s.delete(u)
        await s.commit()
        assert (await s.execute(sa.select(sa.func.count()).select_from(Repository))).scalar_one() == 0


async def test_token_is_stored_encrypted_in_the_db(db, monkeypatch):
    use_settings(monkeypatch, token_encryption_key=Fernet.generate_key().decode())
    async with SessionLocal() as s:
        u = User(github_id=1, login="a", encrypted_access_token=security.encrypt_token("gho_plain"))
        s.add(u)
        await s.commit()
        raw = (await s.execute(sa.text("SELECT encrypted_access_token FROM users"))).scalar_one()
    assert "gho_plain" not in raw and security.decrypt_token(raw) == "gho_plain"


# ---------- auth dependencies ----------

@pytest.fixture
async def auth_client(db, monkeypatch):
    use_settings(monkeypatch, session_secret=SECRET)
    mini = FastAPI()

    @mini.get("/me", response_model=UserOut)
    async def me(user: User = Depends(deps.get_current_user)):
        return user

    @mini.get("/repo/{repo_id}")
    async def repo(repo=Depends(deps.get_user_repo)):
        return {"id": repo.id}

    @mini.get("/ready/{repo_id}")
    async def ready(repo=Depends(deps.get_ready_user_repo)):
        return {"id": repo.id}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mini), base_url="http://t") as c:
        yield c


def cookie(user_id: int) -> dict:
    return {"Cookie": f"session={security.create_session_token(user_id)}"}


async def test_me_requires_a_valid_session(auth_client):
    assert (await auth_client.get("/me")).status_code == 401
    assert (await auth_client.get("/me", headers={"Cookie": "session=garbage"})).status_code == 401
    assert (await auth_client.get("/me", headers=cookie(999))).status_code == 401          # signed, but no such user


async def test_me_returns_public_fields_only(auth_client):
    async with SessionLocal() as s:
        u = User(github_id=5, login="aaryan", encrypted_access_token="secret-cipher", token_scopes="repo")
        s.add(u)
        await s.commit()
    r = await auth_client.get("/me", headers=cookie(u.id))
    assert r.status_code == 200 and r.json()["login"] == "aaryan"
    assert "secret-cipher" not in r.text and "encrypted_access_token" not in r.json()


async def test_repo_ownership_is_enforced_and_hides_existence(auth_client):
    async with SessionLocal() as s:
        a, b = await add_user(s, 1, "a"), await add_user(s, 2, "b")
        mine = Repository(url="https://github.com/o/mine", branch="", owner_id=a.id)
        theirs = Repository(url="https://github.com/o/theirs", branch="", owner_id=b.id)
        legacy = Repository(url="https://github.com/o/legacy", branch="")
        s.add_all([mine, theirs, legacy])
        await s.commit()
    assert (await auth_client.get(f"/repo/{mine.id}")).status_code == 401                 # not signed in
    assert (await auth_client.get(f"/repo/{mine.id}", headers=cookie(a.id))).status_code == 200
    denied = await auth_client.get(f"/repo/{theirs.id}", headers=cookie(a.id))
    missing = await auth_client.get("/repo/9999", headers=cookie(a.id))
    assert denied.status_code == missing.status_code == 404 and denied.json() == missing.json()
    assert (await auth_client.get(f"/repo/{legacy.id}", headers=cookie(a.id))).status_code == 404


async def test_ready_dependency_blocks_unfinished_repos(auth_client):
    async with SessionLocal() as s:
        a = await add_user(s, 1, "a")
        queued = Repository(url="https://github.com/o/q", branch="", owner_id=a.id, status="queued")
        done = Repository(url="https://github.com/o/d", branch="", owner_id=a.id, status="ready")
        s.add_all([queued, done])
        await s.commit()
    assert (await auth_client.get(f"/ready/{queued.id}", headers=cookie(a.id))).status_code == 409
    assert (await auth_client.get(f"/ready/{done.id}", headers=cookie(a.id))).status_code == 200
