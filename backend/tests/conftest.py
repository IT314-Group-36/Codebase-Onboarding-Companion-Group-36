import os
import subprocess
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://onboard:onboard@localhost:5432/onboard_test")
os.environ["EMBED_BACKEND"] = "hash"
os.environ["ALLOW_LOCAL_REPOS"] = "true"
os.environ["GOOGLE_API_KEY"] = ""
os.environ["WORK_DIR"] = "/tmp/onboarding_test_work"

import pytest  # noqa: E402

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
    from alembic import command
    from alembic.config import Config
    import sqlalchemy as sa
    from app.core.config import get_settings
    try:
        eng = sa.create_engine(get_settings().database_url)
        with eng.connect():
            pass
    except Exception as e:  # noqa: BLE001
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
