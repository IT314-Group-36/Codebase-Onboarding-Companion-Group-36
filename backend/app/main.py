import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (registers tables)
from .config import settings
from .database import Base, engine, get_db
from .routers import explore, qa, repos, tasks
from .services.ai_client import ai_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    os.makedirs(settings.repos_dir, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Helps new developers get up to speed on an unfamiliar codebase.\n\n"
        "**Demo flow:** `POST /api/v1/repos` → wait for `status: ready` → "
        "`GET /map` → `GET /files/{path}` → `POST /ask` → `POST /impact` → `GET /onboarding-tasks`."
    ),
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Repositories", "description": "Register and index repositories"},
        {"name": "Explore", "description": "Module map, file explanations, symbols, dependency graph"},
        {"name": "Ask", "description": "Natural-language Q&A and impact analysis"},
        {"name": "Onboarding", "description": "First-week task suggestions"},
        {"name": "System", "description": "Health"},
    ],
)

app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])

for r in (repos.router, explore.router, qa.router, tasks.router):
    app.include_router(r)


@app.get("/health", tags=["System"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "up", "dialect": engine.dialect.name,
            "ai_engine": "connected" if ai_client.enabled else "not configured (heuristic fallback)"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
