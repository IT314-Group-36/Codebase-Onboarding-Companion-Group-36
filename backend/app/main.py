from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.github import router as github_router
from app.api.repos import router as repos_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not hasattr(app.state, "queue"):               # tests inject a fake queue before startup
        app.state.queue = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    if hasattr(app.state.queue, "aclose"):
        await app.state.queue.aclose()


app = FastAPI(title="Codebase Onboarding Companion", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])   # credentials: the session cookie
app.include_router(auth_router)
app.include_router(github_router)
app.include_router(repos_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
