# Codebase Onboarding Companion

Maps an unfamiliar repository, explains key files in plain English, answers questions about the code,
and shows what breaks when a function changes.

Point it at a GitHub repo and it clones it, parses the code, builds a dependency graph, embeds the code
for search, and (with an LLM key) writes a module map and summary. A React app lets you explore the result.

## Current status

| Feature | Status | Notes |
|---|---|---|
| Connect a GitHub repo, public or private | Done | Sign in with GitHub (OAuth); private repos your account can access are cloned with your saved, encrypted token. Connect page has a picker of your GitHub repos and a real branch dropdown (paste-a-URL and token fallback still work) |
| Map of modules and responsibilities | Done | Module map + dependency graph |
| Plain-English explanations | Done | Repo summary, module purposes, architecture paragraph, and per-file / per-function explanations (`/explain`) |
| Ask "where is the payment logic handled?" | Done | Answers do not stream and each question is independent |
| "What would break if I change this function?" | Done | `/impact` plus plain-English impact questions in the Ask box |
| Git history and contribution activity | Done (initial version) | On-demand GitHub history page; latest 50 commits and contributor shares, optionally filtered by top-level folder |
| First-week task list from beginner-friendly issues | Partial | Backend API done (`/issues/sync`, `/onboarding-tasks`); the frontend checklist is still generated locally |

Also still local-only in the frontend: task completion (browser localStorage) and
"remove repository" (hides it in the browser; the API has no delete endpoint).

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

Requires Docker with Compose v2. The app signs users in with GitHub, so a one-time GitHub OAuth app is needed.

1. Create an OAuth app at <https://github.com/settings/developers> (New OAuth App):
   Homepage URL `http://localhost:5173`, Authorization callback URL `http://localhost:5173/api/auth/github/callback`.
   Note the Client ID and generate a Client secret.
2. Create `backend/.env` and generate the server secrets:

```bash
cp backend/.env.example backend/.env
docker compose run --rm api python -m app.core.security     # prints TOKEN_ENCRYPTION_KEY and SESSION_SECRET
```

3. Put `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY` and `SESSION_SECRET` (and optionally your
   free `LLM_API_KEY`) in `backend/.env`, then start everything:

```bash
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
| Login button says GitHub sign-in is not set up | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY` or `SESSION_SECRET` is missing or invalid in `backend/.env`; restart after editing. `http://localhost:8000/auth/config` shows the state |
| GitHub says "redirect_uri is not associated with this application" | The OAuth app's callback URL must be exactly `http://localhost:5173/api/auth/github/callback` (or your `GITHUB_REDIRECT_URI`) |
| Signed in but a private repo fails with "your account cannot access it" | Wrong URL or no access. For an organization repo, an org owner must approve the OAuth app (GitHub org settings, Third-party access) |
| A repo fails with "Sign in with GitHub again" | The saved token was revoked or the encryption key changed. Sign out and sign in again |
| Repos you indexed before login existed are missing | They have no owner yet: see "Repos indexed before login existed" in [backend/README.md](backend/README.md) |
| Indexing fails with "Could not clone the repo" | URL or branch is wrong, or the repo is private and your GitHub account cannot access it (see above) |
| Worker shows `unhealthy` right after start | Normal for up to 3 minutes while the embedding model downloads |
| Frontend cannot reach the backend | Check `docker compose ps`; the web container waits for a healthy api |
| Need a clean slate | `docker compose down -v` |

## Documentation

- [backend/README.md](backend/README.md): API, indexing pipeline, configuration, known limits
- [frontend/README.md](frontend/README.md): pages, services, scripts, running locally or in Docker
