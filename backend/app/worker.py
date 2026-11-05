"""ARQ worker. Run with:  arq app.worker.WorkerSettings"""
import logging

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.services import runtime
from app.services.indexing import run_indexing

logging.basicConfig(level=logging.INFO)


async def startup(ctx):
    ctx["llm"] = runtime.get_llm()
    ctx["embedder"] = runtime.get_embedder()          # model is loaded once per worker process


async def index_repository(ctx, repo_id: int, access_token: str | None = None):
    await run_indexing(repo_id, access_token, llm=ctx["llm"], embedder=ctx["embedder"])


class WorkerSettings:
    functions = [index_repository]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    max_tries = 1                 # an indexing job is replaced wholesale, never retried half-way
    job_timeout = 1800
