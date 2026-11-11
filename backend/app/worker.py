"""ARQ worker. Run with:  arq app.worker.WorkerSettings"""
import logging
from sqlalchemy import select

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.services import runtime
from app.services.indexing import run_indexing
from app.db.session import SessionLocal
from app.models import Repository
from app.services.issues import run_issue_sync

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def startup(ctx):
    ctx["llm"] = runtime.get_llm()
    ctx["embedder"] = runtime.get_embedder()          # model is loaded once per worker process


async def index_repository(ctx, repo_id: int, access_token: str | None = None):
    await run_indexing(repo_id, access_token, llm=ctx["llm"], embedder=ctx["embedder"])
    async with SessionLocal() as session:
        status = (await session.execute(select(Repository.status).where(Repository.id == repo_id))).scalar_one_or_none()
    if status == "ready":
        try:
            await run_issue_sync(repo_id, access_token)
        except Exception:  # best-effort enrichment; indexing remains successful
            log.exception("issue sync after indexing repo %s failed", repo_id)


async def sync_issues(ctx, repo_id: int, access_token: str | None = None):
    await run_issue_sync(repo_id, access_token)


class WorkerSettings:
    functions = [index_repository, sync_issues]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    health_check_interval = 30    # refreshes the redis key that `arq --check` (docker healthcheck) reads
    max_tries = 1                 # an indexing job is replaced wholesale, never retried half-way
    job_timeout = 1800
