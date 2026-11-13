import os
import subprocess
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://onboard:onboard@localhost:5432/onboard_test")
os.environ["EMBED_BACKEND"] = "hash"
os.environ["ALLOW_LOCAL_REPOS"] = "true"
os.environ["GOOGLE_API_KEY"] = ""
os.environ["WORK_DIR"] = "/tmp/onboarding_test_work"

import pytest

REPO_FILES = {
    "README.md": "# Shop\nSmall shop demo with payments.\n",
    "shop/__init__.py": "",
    "shop/db.py": "def save_order(order):\n    return order\n",
    "shop/config.py": 'AWS_KEY = "AKIAABCDEFGHIJKLMNOP"\nDEBUG = False\n',
    "shop/payments.py": (
        "from .db import save_order\n\n"
        "def charge_card(card_number, amount):\n"
        '    """Charge a credit card and record the payment."""\n'
        '    receipt = {"amount": amount, "card": card_number[-4:]}\n'
        "    save_order(receipt)\n"
        "    return receipt\n\n"
        "def refund_payment(order_id):\n"
        '    return save_order({"refund": order_id})\n'),
    "shop/api.py": (
        "from .payments import charge_card\n\n"
        "def checkout(cart):\n"
        "    total = sum(cart)\n"
        '    return charge_card("4111111111111111", total)\n'),
    "web/app.js": "import { getCart } from './cart';\nexport function render() { return getCart(); }\n",
    "web/cart.js": "export function getCart() { return []; }\n",
    ".env": "DB_PASSWORD=supersecret123\n",
}


def make_git_repo(root: Path, files: dict = REPO_FILES) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=root, check=True, env=env, capture_output=True)
    return root


@pytest.fixture
def git_repo(tmp_path) -> Path:
    return make_git_repo(tmp_path / "shop_repo")


@pytest.fixture(scope="session")
def migrated_db():
    """Real Postgres + pgvector: run the Alembic migration, so the migration itself is tested."""
    import sqlalchemy as sa
    from alembic.config import Config

    from alembic import command
    from app.core.config import get_settings
    try:
        eng = sa.create_engine(get_settings().database_url)
        with eng.connect():
            pass
    except Exception as e:
        pytest.skip(f"Postgres not reachable: {e}")
    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent.parent / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture
async def db(migrated_db):
    from sqlalchemy import text

    from app.db.session import engine
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users, repositories RESTART IDENTITY CASCADE"))
    yield


# ---------------------------------------------------------------------------------------------
# Auth / GitHub test helpers
# ---------------------------------------------------------------------------------------------
import httpx


class FakeQueue:
    """Stands in for the arq/Redis pool: records the jobs the API enqueues."""

    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, name, *args):
        self.jobs.append((name, args))


class FakeGitHub:
    """Programmable stand-in for github.com and api.github.com (used through httpx.MockTransport).

    Set `token_response`, `user`, `repos`, `branches`, `valid_token`, or `force_status` to shape the answers;
    every request is recorded in `requests`."""

    def __init__(self):
        self.requests = []
        self.token_response = {"access_token": "gho_testtoken", "scope": "repo,read:user", "token_type": "bearer"}
        self.user = {"id": 4242, "login": "octo", "name": "Octo Cat", "email": "octo@example.com",
                     "avatar_url": "https://avatars.example/octo.png"}
        self.valid_token = "gho_testtoken"           # any other bearer token gets a 401 (a revoked token)
        self.repos: list[dict] = []
        self.branches: dict[str, list[str]] = {}     # "owner/name" -> branch names; missing key -> 404
        self.default_branch = "main"
        self.force_status: int | None = None         # answer every API call with this status
        self.commits: list[dict] = []                # /repos/<o>/<r>/commits answer
        self.commits_empty = False                   # True -> 409 "Git Repository is empty."

    def client(self):
        from app.services.github import GitHubClient
        return GitHubClient(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url, path = request.url, request.url.path
        if url.host == "github.com" and path == "/login/oauth/access_token":
            return httpx.Response(200, json=self.token_response)
        if self.force_status:
            headers = {"x-ratelimit-remaining": "0"} if self.force_status in (403, 429) else {}
            return httpx.Response(self.force_status, json={"message": "forced"}, headers=headers)
        if request.headers.get("authorization") != f"Bearer {self.valid_token}":
            return httpx.Response(401, json={"message": "Bad credentials"})
        if path == "/user":
            return httpx.Response(200, json=self.user)
        if path == "/user/repos":
            page, per = int(url.params.get("page", 1)), int(url.params.get("per_page", 30))
            chunk = self.repos[(page - 1) * per: page * per]
            headers = {"link": f'<https://api.github.com/user/repos?page={page + 1}>; rel="next"'} if page * per < len(self.repos) else {}
            return httpx.Response(200, json=[_gh_repo(x) for x in chunk], headers=headers)
        parts = path.strip("/").split("/")
        if parts[0] == "repos" and len(parts) in (3, 4):
            full = f"{parts[1]}/{parts[2]}"
            if len(parts) == 4 and parts[3] == "commits":
                if self.commits_empty:
                    return httpx.Response(409, json={"message": "Git Repository is empty."})
                return httpx.Response(200, json=self.commits)
            if full not in self.branches:
                return httpx.Response(404, json={"message": "Not Found"})
            if len(parts) == 3:
                return httpx.Response(200, json={"default_branch": self.default_branch})
            return httpx.Response(200, json=[{"name": b} for b in self.branches[full]])
        return httpx.Response(404, json={"message": "Not Found"})


def _gh_repo(name: str) -> dict:
    owner = name.split("/")[0]
    return {"full_name": name, "html_url": f"https://github.com/{name}", "private": name.endswith("-private"),
            "default_branch": "main", "description": f"About {name}", "language": "Python",
            "pushed_at": "2026-11-01T10:00:00Z", "owner": {"login": owner}}


def api_client(headers: dict | None = None) -> httpx.AsyncClient:
    from app.main import app
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=headers or {})


@pytest.fixture
def auth_settings(monkeypatch):
    """Working login secrets and GitHub app settings, patched into every module that reads them."""
    from cryptography.fernet import Fernet

    from app.api import auth as auth_api
    from app.api import deps
    from app.core import security
    from app.core.config import Settings
    from app.services import github
    cfg = Settings(session_secret="s" * 48, token_encryption_key=Fernet.generate_key().decode(),
                   github_client_id="test-client-id", github_client_secret="test-client-secret",
                   github_redirect_uri="http://localhost:5173/api/auth/github/callback", frontend_url="http://localhost:5173")
    for mod in (security, deps, auth_api, github):
        monkeypatch.setattr(mod, "get_settings", lambda: cfg)
    return cfg


@pytest.fixture
def fake_github(auth_settings):
    from app.api import deps
    from app.main import app
    gh = FakeGitHub()
    app.dependency_overrides[deps.get_github_client] = gh.client
    yield gh
    app.dependency_overrides.pop(deps.get_github_client, None)


@pytest.fixture
def make_user(auth_settings):
    """async make_user(github_id=1, login="tester", token=None) -> (User, headers carrying a valid session cookie)."""
    from app.core.security import create_session_token, encrypt_token
    from app.db.session import SessionLocal
    from app.models import User

    async def _make(github_id: int = 1, login: str = "tester", token: str | None = None):
        async with SessionLocal() as s:
            u = User(github_id=github_id, login=login, encrypted_access_token=encrypt_token(token) if token else None,
                     token_scopes="repo" if token else None)
            s.add(u)
            await s.commit()
        return u, {"Cookie": f"session={create_session_token(u.id)}"}
    return _make
