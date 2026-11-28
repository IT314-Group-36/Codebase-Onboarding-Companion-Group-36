import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.github import router as github_router
from app.api.history import router as history_router
from app.api.repos import router as repos_router
from app.api.tasks import router as tasks_router
from app.core.config import get_settings
from app.db.session import engine
from app.services.jobs import InProcessQueue, recover_interrupted_jobs

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    own_queue = not hasattr(app.state, "queue")       # tests inject a fake queue before startup
    if own_queue:
        await recover_interrupted_jobs()              # jobs cut off by a restart would otherwise stay "indexing" forever
        app.state.queue = InProcessQueue(settings.max_concurrent_indexing, settings.job_timeout_seconds)
    yield
    if hasattr(app.state.queue, "aclose"):
        await app.state.queue.aclose()
    if own_queue:
        del app.state.queue


def docs_urls(enabled: bool) -> dict:
    """The interactive API documentation lists the whole API for anyone to study, so it is opt-in (ENABLE_DOCS)."""
    return {} if enabled else {"docs_url": None, "redoc_url": None, "openapi_url": None}


app = FastAPI(title="Codebase Onboarding Companion", version="0.2.0", lifespan=lifespan,
              **docs_urls(get_settings().enable_docs))
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])   # credentials: the session cookie
app.include_router(auth_router)
app.include_router(github_router)
app.include_router(history_router)
app.include_router(repos_router)
app.include_router(tasks_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    """Bounded database readiness probe; never expose connection errors or credentials."""
    headers = {"Cache-Control": "no-store"}
    try:
        # Includes pool checkout, reconnect/pre-ping, query and connection cleanup.
        async with asyncio.timeout(3):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503, headers=headers)
    body = {"status": "ready"}
    revision = os.environ.get("RENDER_GIT_COMMIT", "")
    if re.fullmatch(r"[0-9a-f]{40}", revision):
        body["revision"] = revision
    return JSONResponse(body, headers=headers)
