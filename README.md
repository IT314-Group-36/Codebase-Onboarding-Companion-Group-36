# Codebase Onboarding Companion

Helps a new developer get up to speed on an unfamiliar codebase: a navigable module map, plain-English
file explanations, natural-language questions ("where is the payment logic handled?"), change-impact
analysis ("what would break if I change this?"), and a suggested first-week plan.

```
 Browser ──► Frontend (static, :3000) ──► Backend (FastAPI, :8000) ──► AI engine (FastAPI, :9000)
                                              │                            └─ Gemini API (optional)
                                              └─ SQLite (default) or PostgreSQL
```

| Part | Team | Folder | What it is |
|---|---|---|---|
| Frontend | Frontend | `frontend/` | Static SPA (vanilla JS ES modules, no build step) |
| Backend | Backend | `backend/` | REST API, repo indexing, search, impact analysis, DB |
| AI engine | AI API | `ai_engine/` | `POST /v1/generate`: explanations and answers. Uses Google Gemini if a key is set, otherwise offline heuristics |

## Run everything (one command)

Needs Python 3.10+ (and `git` only if you index remote repos).

**With uv**
```bash
uv sync
uv run python run.py
```

**With pip**
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Then open:
- **App:** http://localhost:3000
- **Backend API docs (Swagger):** http://localhost:8000/docs
- **AI engine docs:** http://localhost:9000/docs

Click **"Index this project as a demo"** on the welcome screen. It indexes the project itself
(`..` relative to `backend/`), so you can immediately explore the Python and JavaScript code.
Ctrl-C stops all three services.

You can also run the services separately:
```bash
cd ai_engine && uv run uvicorn app.main:app --port 9000
cd backend   && AI_API_URL=http://127.0.0.1:9000/v1/generate uv run uvicorn app.main:app --port 8000
python -m http.server 3000 --directory frontend
```

## Configuration (optional)

Copy `.env.example` to `.env` in the project root; `run.py` loads it.

- **PostgreSQL:** `docker compose up -d`, then set
  `DATABASE_URL=postgresql+psycopg2://onboard:onboard@localhost:5432/onboarding` in `.env`.
  Tables are created automatically. Inspect with
  `docker exec -it onboarding-db psql -U onboard -d onboarding -c "\dt"`.
- **Real LLM answers:** set `GEMINI_API_KEY` (free key from https://aistudio.google.com/apikey; model via `GEMINI_MODEL`). Without it the engine uses
  deterministic offline heuristics, and the UI labels which one answered.
- **GitHub starter issues:** set `GITHUB_TOKEN` to avoid rate limits.
- **Engine auth:** set `ENGINE_API_KEY` and the backend sends it as a Bearer token automatically.

## Using the app

1. **Map:** modules, their responsibilities, key files.
2. **Files:** explanation, symbols, imports / imported-by, and source viewer for each file.
3. **Ask:** natural-language questions with source links; history is stored in the database.
4. **Impact:** enter a file path or a function name; get direct and transitive dependents, tests to run, and a risk level.
5. **Graph:** dependency graph at module or file level; click a node to open it.
6. **First week:** a 5-day plan plus starter tasks (GitHub "good first issue"s for GitHub repos, otherwise TODOs and undocumented functions).

## Tests

```bash
cd backend   && uv run pytest        # end-to-end API test (indexes this project)
cd ai_engine && uv run pytest        # engine tests
# UI smoke test (needs the stack running: python run.py)
cd frontend  && npm install && npm test
```

## Contract between backend and AI engine

```
POST {AI_API_URL}      (default http://127.0.0.1:9000/v1/generate)
Authorization: Bearer <ENGINE_API_KEY>      (only if configured)

{"task": "explain_file",    "input": {"path", "language", "code", "symbols": [{"name","kind","signature"}]}}
{"task": "answer_question", "input": {"question", "contexts": [{"path","summary","reason","symbols"}]}}

-> {"output": "<plain-English text>", "provider": "gemini" | "offline"}
```
If the engine is down or errors, the backend falls back to built-in summaries and keyword search, so the app keeps working.

## Backend endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | DB + AI engine status |
| POST | `/api/v1/repos` | Register a repo (git URL or server path) and index in the background (202) |
| GET | `/api/v1/repos`, `/api/v1/repos/{id}` | List / status |
| POST | `/api/v1/repos/{id}/reindex` | Re-index |
| DELETE | `/api/v1/repos/{id}` | Delete repo + indexed data |
| GET | `/api/v1/repos/{id}/map` | Module map |
| GET | `/api/v1/repos/{id}/files` | List/filter files (`module`, `language`, `q`) |
| GET | `/api/v1/repos/{id}/files/{path}` | File explanation |
| GET | `/api/v1/repos/{id}/source?path=` | Raw source |
| GET | `/api/v1/repos/{id}/symbols` | Search functions/classes |
| GET | `/api/v1/repos/{id}/graph?level=module\|file` | Dependency graph |
| POST | `/api/v1/repos/{id}/ask` | Natural-language question |
| GET | `/api/v1/repos/{id}/questions` | Question history |
| POST | `/api/v1/repos/{id}/impact` | Change-impact analysis |
| GET | `/api/v1/repos/{id}/onboarding-tasks` | First-week plan + starter tasks |

## Known limits

- Analysis is static: full symbol parsing for Python, regex-level for JS/TS, file-level info only for other languages. Dynamic imports and runtime wiring are not detected.
- Question answering is keyword/symbol based, with an LLM (if configured) writing the final answer from the retrieved files; there are no embeddings yet.
- Indexing runs in-process as a background task. Use Celery/RQ for very large repos.
- No user authentication yet. The `..`/local-path source option lets API callers index any folder the server can read, so set `ALLOW_LOCAL_PATHS=false` for any shared deployment.
- The PostgreSQL path and the live Gemini API call are implemented but were not exercised in my test environment (SQLite and the offline engine were).
