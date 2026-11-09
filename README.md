# Codebase Onboarding Companion

Maps an unfamiliar repository, explains key files in plain English, answers questions about the code,
and shows what breaks when a function changes.

Point it at a GitHub repo and it clones it, parses the code, builds a dependency graph, embeds the code
for search, and (with an LLM key) writes a module map and summary. A React app lets you explore the result.

## Current status

| Feature | Status | Notes |
|---|---|---|
| Connect a public GitHub repo | Done | Private repos only work by pasting a token per request (OAuth login in progress) |
| Map of modules and responsibilities | Done | Module map + dependency graph |
| Plain-English explanations | Partial | Repo summary, module purposes and an architecture paragraph; nothing per file or function yet |
| Ask "where is the payment logic handled?" | Done | Answers do not stream and each question is independent |
| "What would break if I change this function?" | Partial | `/impact` works if you pick the symbol; the Ask box does not use the graph yet |
| First-week task list from beginner-friendly issues | Not built | No GitHub issues code yet |

Also still local-only in the frontend: sign-in (a placeholder session, no real GitHub OAuth), task completion
(browser localStorage) and "remove repository" (hides it in the browser; the API has no delete endpoint).

## Repository layout

```
.
├── backend/                 FastAPI API + AI pipeline (details: backend/README.md)
│   ├── app/                 FastAPI app: api/, core/, db/, services/, models.py, schemas.py, worker.py
│   ├── ai_pipeline/         parser, graph, chunker, embeddings, LLM chains (imported by app/)
│   ├── alembic/             database migrations
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml, uv.lock
│   └── .env.example
├── frontend/                React + Vite app (details: frontend/README.md)
│   ├── Dockerfile           dev stage (Vite) and prod stage (nginx)
│   └── nginx.conf           serves the build and proxies /api to the api container
├── docker-compose.yml       db (pgvector), redis, migrate, api, worker, web
├── docker-compose.dev.yml   development overrides: hot reload for api, worker and web
├── .env.example             optional compose settings (WEB_PORT)
└── .gitignore
```

## How the pieces fit

```
browser ──> web (nginx :5173) ──/api/*──> api (FastAPI :8000) ──> db (Postgres + pgvector)
                                              │
                                              └──> redis ──> worker (arq): clone, parse, embed, LLM steps
```

The API returns immediately when you register a repo; the worker does the indexing and the UI polls
`GET /repos/{id}` for progress.

## Quick start (Docker, whole stack)

Requires Docker with Compose v2.

```bash
cp backend/.env.example backend/.env      # optional: put your free LLM_API_KEY in it
docker compose up --build
```

| What | URL |
|---|---|
| Web app | http://localhost:5173 (change the port with `WEB_PORT` in a root `.env`) |
| API docs (Swagger) | http://localhost:8000/docs |

The first start is slow: the worker downloads the embedding model (about 130 MB) once and caches it in a Docker volume.
Without `LLM_API_KEY` everything works except `/ask` and `/impact?explain=true`.

Stop with `Ctrl+C`. To also delete the database and the model cache: `docker compose down -v`.

## Development with hot reload

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Edits under `backend/app` and `backend/ai_pipeline` restart the api and worker automatically, and frontend edits
appear through Vite HMR. The URLs are the same as above.

## Running without Docker (optional)

Run only the infrastructure in Docker, and the apps on your machine:

```bash
docker compose up db redis
cd backend && uv sync && uv run alembic upgrade head
uv run uvicorn app.main:app --reload          # terminal 1
uv run arq app.worker.WorkerSettings          # terminal 2
cd frontend && npm install && npm run dev     # terminal 3, http://localhost:5173
```

Vite proxies `/api` to `http://localhost:8000` in this mode. See the backend and frontend READMEs for details.

## Configuration

Backend settings live in `backend/.env` (see the table in [backend/README.md](backend/README.md#configuration)).
Never commit `.env` files; only `.env.example` files are tracked.

## Tests and checks

```bash
cd backend && uv run pytest        # needs Postgres with pgvector; skipped otherwise
cd frontend && npm run lint && npm run build
```

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Port 5173, 8000 or 5432 already in use | Stop the other process, or set `WEB_PORT` for the web app |
| `/ask` returns 503 | `LLM_API_KEY` is not set in `backend/.env` (restart the stack after adding it) |
| Indexing fails with "Could not clone the repo" | The repo is private or the URL/branch is wrong. For private repos paste a GitHub token with read access |
| Worker shows `unhealthy` right after start | Normal for up to 3 minutes while the embedding model downloads |
| Frontend cannot reach the backend | Check `docker compose ps`; the web container waits for a healthy api |
| Need a clean slate | `docker compose down -v` |

## Documentation

- [backend/README.md](backend/README.md): API, indexing pipeline, configuration, known limits
- [frontend/README.md](frontend/README.md): pages, services, scripts, running locally or in Docker
