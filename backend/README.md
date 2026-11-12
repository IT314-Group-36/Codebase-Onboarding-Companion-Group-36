# Codebase Onboarding Companion: backend + AI pipeline

FastAPI + Alembic + Postgres/pgvector + ARQ (Redis) + tree-sitter + NetworkX. Everything here runs on free
tools: local ONNX embeddings (fastembed), the Gemini free tier for the LLM steps (through LangChain), no paid service required.

## Run it

From the repository root:

```bash
cp backend/.env.example backend/.env   # put your free LLM_API_KEY in it (optional, see below; the old name GOOGLE_API_KEY still works)
docker compose up --build              # db, redis, migrations, api (:8000), worker, web (:5173)
```

Then open http://localhost:8000/docs for the API, or http://localhost:5173 for the web app.
For hot reload while developing: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`.

Without Docker for the backend itself (uv only, no pip/venv/requirements.txt): start Postgres with the pgvector extension and Redis
(`docker compose up db redis` does exactly that), then
```bash
cd backend
uv sync                                   # creates .venv from uv.lock
uv run alembic upgrade head
uv run uvicorn app.main:app --reload      # terminal 1
uv run arq app.worker.WorkerSettings      # terminal 2
```
Add a dependency with `uv add <pkg>`; commit `pyproject.toml` and `uv.lock` together. First indexing downloads the embedding model (~130 MB) once.

No `LLM_API_KEY`? Everything still works except general `/ask` questions and `/impact?explain=true` (503); "what would break if I change X?" questions in `/ask` are answered from the graphs without a key. `/explain` still returns the
relationships ("uses X, used by Y"); only the prose is left out. The module map falls back
to a deterministic one built from the import graph, and the repo summary is skipped (with a warning in the response).

Tests (real Postgres + pgvector needed, they skip otherwise): `cd backend && uv run pytest`
(point `DATABASE_URL` at a scratch database; the suite runs the Alembic migration up and down).

## API

| Method | Path | What |
|---|---|---|
| GET | `/health` | liveness check (used by the Docker healthcheck) |
| GET | `/auth/config` | `{github_login_enabled}`: whether GitHub sign-in is set up on this server |
| GET | `/auth/github/login` | start sign-in: redirects to GitHub (sets a short-lived `oauth_state` cookie) |
| GET | `/auth/github/callback` | GitHub returns here; creates/updates the user, saves the token encrypted, sets the session cookie, redirects to the frontend |
| GET | `/auth/me` | the signed-in user (401 if not signed in); `github_connected` says a token is saved |
| POST | `/auth/logout` | clears the session cookie |
| GET | `/github/repos?page=&per_page=&q=` | repos the signed-in user can access on GitHub (public and private); `q` filters the page |
| GET | `/github/branches?repo=owner/name` | default branch and branch names (first 100) |
| POST | `/repos` | `{url, branch?, access_token?}` register + enqueue indexing (202). Idempotent per user+url+branch |
| POST | `/repos/{id}/reindex` | re-run indexing (atomic swap, old data stays readable until done) |
| GET | `/repos`, `/repos/{id}` | status (`queued/indexing/ready/failed`), `stage`, `error`, summary, tech stack, report, warnings |
| GET | `/repos/{id}/map` | modules (each with `depends_on`, `used_by`, `relationship_summary`), entry points, module-to-module dependency graph (for React Flow) |
| GET | `/repos/{id}/files`, `/files/{path}` | file tree; per file: symbols, imports, imported_by |
| GET | `/repos/{id}/explain?file=\|symbol=&refresh=` | beginner-friendly explanation of one file or function + how it relates to the rest (see below) |
| GET | `/repos/{id}/symbols?q=` | find functions/classes |
| POST | `/repos/{id}/search` | hybrid retrieval, no LLM: `{query, k}` |
| POST | `/repos/{id}/ask` | `{question, symbol?, file?, depth?}`: "what would break if I change X?" is answered from the import/call graphs; any other question is RAG with validated citations (see below) |
| GET | `/repos/{id}/impact?symbol=\|file=&depth=&explain=` | "what breaks if I change this" (reverse traversal); same report the Ask box shows, with a call chain and a reason per item |

Every `/repos` and `/github` route needs the session cookie (401 otherwise), and a user only ever sees their own
repositories: someone else's repo answers 404, the same as a missing one. Poll `GET /repos/{id}` for progress; the
other repo endpoints return 409 until `status == "ready"`.

Errors worth handling in a client: `403` with `detail.code == "github_reauth_required"` (the saved GitHub token was
revoked or can no longer be read: sign in with GitHub again), `429` (GitHub rate limit), `404` (not found or not
accessible with this GitHub account).

### Private repositories

Sign in with GitHub and register the repo URL: nothing else is needed. The worker first tries an anonymous clone
(so public repos never use your token, and a revoked token cannot break them); if that fails it clones with the token
saved at sign-in. The token is decrypted only inside the worker for that clone and is never put in the job queue,
logs or API responses. Pasting a token as `access_token` on `POST /repos` or `/reindex` still works and takes
priority; that one is passed through the queue for the job and never stored.

A failed clone says which problem it is: "sign in with GitHub again" (token rejected), or "your account cannot access it"
(wrong URL, no permission, or an organization that has not approved this OAuth app).

## Configuration

Set these in `backend/.env` (environment variables of the same name also work). Defaults are in `app/core/config.py`.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_API_KEY` | empty | LLM key (`GOOGLE_API_KEY` also accepted). Empty means no `/ask`, no summary |
| `LLM_MODEL` | `google_genai:gemini-3.6-flash` | `<provider>:<model>` (LangChain) |
| `LLM_MIN_INTERVAL_SECONDS` | `4` | spacing between LLM calls (free-tier rate limits) |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | `60`, `4` | per-call timeout and retries |
| `DATABASE_URL` | local Postgres | overridden by `docker-compose.yml` inside Docker |
| `REDIS_URL` | `redis://localhost:6379` | job queue; overridden by compose inside Docker |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON list; only matters when the browser calls the API directly. Compose also sets it, which takes precedence over `.env` |
| `EMBED_BACKEND`, `EMBED_MODEL`, `EMBED_DIM` | `fastembed`, `BAAI/bge-small-en-v1.5`, `384` | embeddings; `hash` backend is for tests only |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | empty | GitHub OAuth app credentials (for login and private repos) |
| `GITHUB_REDIRECT_URI` | `http://localhost:5173/api/auth/github/callback` | must match the OAuth app's callback URL exactly |
| `FRONTEND_URL` | `http://localhost:5173` | where the browser is sent after login |
| `SESSION_SECRET` | empty | signs the login cookie; at least 32 characters |
| `SESSION_COOKIE_NAME`, `SESSION_TTL_SECONDS`, `COOKIE_SECURE` | `session`, 7 days, `false` | cookie settings; set `COOKIE_SECURE=true` behind https |
| `TOKEN_ENCRYPTION_KEY` | empty | Fernet key that encrypts stored GitHub tokens; comma-separate several keys to rotate |
| `MAX_CHUNKS`, `MAX_FILE_BYTES` | `5000`, `200000` | indexing caps |
| `WORK_DIR` | `/tmp/onboarding_work` | where clones live during a job (deleted afterwards) |
| `ALLOW_LOCAL_REPOS` | `false` | accept local directory paths instead of GitHub URLs (tests and demos only) |

## GitHub sign-in, users and ownership

**One-time setup** (each developer or deployment):

1. Create an OAuth app at <https://github.com/settings/developers> (New OAuth App). Homepage URL
   `http://localhost:5173`, Authorization callback URL `http://localhost:5173/api/auth/github/callback`.
   Generate a client secret.
2. Generate the two server secrets: `docker compose run --rm api python -m app.core.security`
   (or `cd backend && uv run python -m app.core.security`).
3. Put `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY` and `SESSION_SECRET` in `backend/.env`
   and restart the stack. `GET /auth/config` should now say `{"github_login_enabled": true}`.

How it works: the browser goes to `/auth/github/login`, GitHub asks the user to approve read access (scope
`repo read:user`; GitHub has no read-only private-repo scope for OAuth apps, but the code only ever reads), then calls
`/auth/github/callback`. The backend checks the one-time `state`, exchanges the code for a token, upserts the user by
GitHub id, stores the token encrypted (Fernet), and sets a signed, HttpOnly, SameSite=Lax session cookie holding only
the user id. Logging in again replaces the saved token and profile.

Database (migration `0002`): `users` (GitHub id, login, profile, encrypted token, scopes) and `repositories.owner_id`.
Uniqueness is per owner, so two users can index the same repo separately.

| Piece | Where |
|---|---|
| OAuth routes, session cookie | `app/api/auth.py` |
| GitHub API client (code exchange, repos, branches) | `app/services/github.py` |
| Token encryption (rotation via several comma-separated keys), signed session token | `app/core/security.py` |
| `get_current_user` (401), `get_user_repo` (404 for someone else's repo), `get_ready_user_repo` (409) | `app/api/deps.py` |
| Saved-token clone fallback | `app/services/indexing.py` |

Security notes: the state cookie prevents login CSRF; `SameSite=Lax` stops other sites from making authenticated POSTs;
only a fixed allow-list of GitHub error codes is shown back to users; a revoked or unreadable token produces a
"sign in again" message instead of a crash. Set `COOKIE_SECURE=true` when serving over https.

**Repos indexed before login existed** have no owner and are hidden from everyone. Give them to a user (after that
user has signed in once):

```bash
docker compose exec db psql -U onboard -c "UPDATE repositories SET owner_id = (SELECT id FROM users WHERE login = 'YOUR_GITHUB_LOGIN') WHERE owner_id IS NULL"
```

### `/explain` response

`GET /repos/{id}/explain?file=src/app.py` or `?symbol=<uid or name>` (exactly one). A name that matches several symbols returns 409 with `candidates`.

| Field | Meaning |
|---|---|
| `relationship_summary` | one sentence, always present: ``"`a.py` uses `b.py`, and is used by `c.py`."`` (functions: calls / called by) |
| `relationships` | the same facts as data: `uses`, `used_by`, `calls_into`, `called_from`, `symbols` (file) or `calls`, `called_by` (function) |
| `explanation` | LLM prose (`summary`, `explanation`, `how_it_fits`, plus `key_symbols` for files or `inputs_outputs` for functions); `null` without an LLM key, for sensitive files, or for files with no indexed text. Always see `warnings` |
| `source` | `llm` (just generated), `cache`, or `none` |
| `module` | the module-map entry the file belongs to (name, path, purpose) |

Relationships are computed from the stored graphs, so they are never invented; the LLM only writes prose around them and any symbol name it makes up is dropped.
Explanations are cached per repo (table `explanations`, dropped on reindex, ignored if the commit changed); `refresh=true` regenerates.

### Asking "what would break if I change X?" in the Ask box

Send the normal `POST /repos/{id}/ask` body. The backend decides whether the question is an impact question (no extra LLM call),
finds the function, file or folder it names (`charge_card`, `` `Serializer.dumps` ``, `shop/db.py`, `core/`, "the payments module"),
runs the reverse-graph impact analysis and answers in plain English. Nothing has to be selected first.

| Request field | Meaning |
|---|---|
| `question` | required, as before |
| `symbol` / `file` | optional: what the question is about (a uid, a name or a path). Use it to answer a clarification, or when the UI already knows the selection ("this function") |
| `depth` | optional, 1 to 6, default 3 ("directly" in the question means 1) |

Every response now has `intent`: `"impact"` or `"question"`. Normal questions keep the Sprint 1 fields (`answer`, `citations`, `sources`).

| Impact response field | Meaning |
|---|---|
| `answer` | plain-English answer: LLM prose when a key is set (grounded in the facts below), otherwise the deterministic `impact.summary` |
| `needs_clarification`, `candidates` | `true` when the name is ambiguous or missing ("the serializer" matches a class and a test fixture, "the payment logic" names nothing). Show `candidates` as buttons and ask again with `symbol` or `file` set to the choice |
| `impact.target`, `impact.target_info` | what was analysed (`kind` is `symbol`, `file` or `module` for a folder) |
| `impact.affected_symbols[]` | `qualname`, `path`, `start_line`, `distance`, `chain` (names from the affected function down to the target), `reason`, `is_test` |
| `impact.affected_files[]` | `path`, `distance`, `reason`, `is_test` |
| `impact.affected_tests[]` | test files that reach the target |
| `impact.dependencies` | what the target itself calls (`calls`) and imports (`imports`) |
| `impact.totals`, `impact.summary` | counts and the deterministic text |
| `citations` | the target plus its direct callers (path and line) |
| `warnings`, `caveat` | no LLM key, LLM failed (the structured answer is still returned), other names in the question that were not analysed; static-analysis caveat |

Unknown `symbol` or `file`: 404. `depth` out of range: 422. If the LLM call fails for an impact question the structured answer is still returned with a warning (general questions still return 502).

## How indexing works

clone (shallow, token via env) -> scan (skip symlinks/sensitive files) -> redact secrets in content ->
tree-sitter parse (Python, JS/JSX, TS/TSX) -> NetworkX import graph + call graph -> rank files ->
symbol-aware chunks -> local embeddings -> one atomic DB swap -> LLM module map + summary (validated, with fallback).

## What changed vs. the first AI-team version

| Problem | Fix |
|---|---|
| `index_repo` wiped the shared `vector_store` folder on every run | pgvector rows keyed by `repo_id`; reindex replaces one repo atomically |
| `.env` never loaded; embedding model reloaded on every call | settings via pydantic-settings; embedder and LLM are process singletons |
| Chroma on local disk, unsafe across API + worker processes | Postgres + pgvector (exact cosine search, filtered by repo) + Postgres full-text, fused with RRF |
| torch + MiniLM (256-token window, general text) | fastembed/ONNX, `bge-small` (512 tokens); code model `jina-embeddings-v2-base-code` is a config switch |
| Random sampling at the chunk cap | files ranked (README, entry points, import-graph hubs first, tests last) |
| Character-based chunks | tree-sitter chunks per function/method/class header, exact line ranges |
| LLM guessed structure from names | import-graph facts (hubs, entry candidates, folder dependencies) go into the prompt; paths validated |
| Everything synchronous | async LLM calls; blocking work in threads; ARQ + Redis job queue |
| Free-tier rate limits | min-interval throttle, concurrency cap, retry with backoff, graceful fallback if the LLM fails |
| Secrets matched by filename only | content redaction (AWS, GitHub, Google, Slack, Stripe, JWT, private keys, high-entropy assignments) |
| URL passed straight to `git` | https GitHub allowlist, branch validation, `--` separator, per-job temp dir, symlinks never followed, token never in argv |
| Repo text could prompt-inject the LLM | prompts mark repository content as untrusted data; every returned path/citation is validated |
| Unpinned requirements | `pyproject.toml` + `uv.lock`; LangChain pinned `>=1,<2` (1.0 promises no breaking changes until 2.0) |

## LangChain in this project: where each piece lives

| LangChain piece | Where | Notes |
|---|---|---|
| Chat model (`init_chat_model`) | `ai_pipeline/llm.py` `build_chat_model` | provider + model come from `LLM_MODEL`; rate limiter, timeout and retries are LangChain's |
| Prompts (`ChatPromptTemplate`) | `module_map.py`, `summary.py`, `app/services/qa.py` | all prompts mark repository text as untrusted data |
| Structured output | `llm.py` `structured_chain` | `prompt \| model.with_structured_output(Schema)`, one retry on malformed output |
| `Embeddings` interface | `ai_pipeline/embeddings.py` | fastembed locally; swap in any LangChain embeddings class |
| `Document` | `chunker.py` | one Document per function/class, metadata carries file path and exact lines |
| `BaseRetriever` | `app/services/retrieval.py` `PgHybridRetriever` | wraps OUR pgvector + full-text SQL; the vector store itself is not LangChain's |

Deliberately NOT LangChain: the pgvector tables and hybrid SQL, tree-sitter chunking (LangChain's splitters cannot give
function-level chunks with exact line numbers), and the NetworkX graphs.

## Known limits (honest list)

- Impact analysis follows calls and imports only: subclasses, `except SomeError` handlers and `isinstance` checks are not edges, so changing a class or exception can affect more than the list shows.
- Call/impact analysis is static and name-based: dynamic dispatch, reflection and string imports are invisible, and a
  call to an unknown receiver (`x.save()`) only resolves inside the same file or imported files. The API says so in `caveat`.
- Only Python, JS/JSX and TS/TSX are parsed; other languages are indexed as line-window text chunks (still searchable).
- Whole files are not stored after indexing (the clone is deleted, DR-03); only the parsed symbols, graph edges and embedded code chunks are kept in the database. The UI cannot show full source yet.
- Secret redaction is regex-based. For production add gitleaks in the worker.
- `tree-sitter` is pinned `<0.26`: 0.26.0 segfaulted in the Python binding on larger files.
- Changing `EMBED_DIM` needs a new Alembic migration and a reindex of every repo.
- `google_genai:gemini-3.6-flash` is the default `LLM_MODEL`: confirm in AI Studio that it is available on your free tier.
- Old `.env` files: `GOOGLE_API_KEY` still works, but `GEMINI_MODEL` is ignored now. Use `LLM_MODEL=google_genai:<model>`.
- Not built yet: first-week task list from GitHub issues, per-file and per-function explanations, graph-aware answers in `/ask`
  ("what breaks if I change X" in plain English), streaming and follow-up questions for `/ask`, a repo delete endpoint,
  webhook re-indexing. There is no "disconnect GitHub" endpoint yet (revoke the app on GitHub to cut access).
- Private-repo access uses GitHub's broad `repo` OAuth scope (read and write at GitHub's end; this app only reads). A
  GitHub App with per-repo installs would be the least-privilege upgrade.
- Organizations that restrict third-party apps must approve this OAuth app before their private repos can be cloned.

## Later, when you move to paid services

- Gemini paid tier: only billing and `LLM_MIN_INTERVAL_SECONDS` change.
- Hosted embeddings (Voyage, Google, OpenAI): return any LangChain `Embeddings` class from `get_embedder()` in
  `ai_pipeline/embeddings.py`, set `EMBED_DIM`, add a migration if the size differs, reindex.
- Large repos: add an HNSW index (pgvector >= 0.8 with iterative scans), or move vectors to Qdrant.
