# Codebase Onboarding Companion: backend + AI pipeline

FastAPI + Alembic + Postgres/pgvector + in-process background jobs + tree-sitter + NetworkX. Everything here runs on free
tools: Cloudflare Workers AI embeddings and the Gemini free tier for the LLM steps (through LangChain), no paid service required.

## Run it

From the repository root:

```bash
cp backend/.env.example backend/.env   # set CF_ACCOUNT_ID and CF_API_TOKEN (required, see "Cloudflare Workers AI embeddings" below) and optionally your free LLM_API_KEY (the old name GOOGLE_API_KEY still works)
docker compose up --build              # db, migrations, api (:8000), web (:5173)
```

Then open http://localhost:8000/docs for the API, or http://localhost:5173 for the web app.
For hot reload while developing: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`.

Without Docker for the backend itself (uv only, no pip/venv/requirements.txt): start Postgres with the pgvector extension
(`docker compose up db` does exactly that), then
```bash
cd backend
uv sync                                   # creates .venv from uv.lock
uv run alembic upgrade head
uv run uvicorn app.main:app --reload      # terminal 1
```
Add a dependency with `uv add <pkg>`; commit `pyproject.toml` and `uv.lock` together.

No `LLM_API_KEY`? Everything still works except general `/ask` questions and `/impact?explain=true` (503); "what would break if I change X?" questions in `/ask` are answered from the graphs without a key. `/explain` still returns the
relationships ("uses X, used by Y"); only the prose is left out. The module map falls back
to a deterministic one built from the import graph, and the repo summary is skipped (with a warning in the response).

Tests (real Postgres + pgvector needed, they skip otherwise): `cd backend && uv run pytest`
(point `DATABASE_URL` at a scratch database; the suite runs the Alembic migration up and down).

## API

| Method | Path | What |
|---|---|---|
| GET | `/health` | liveness only; does not contact the database |
| GET | `/ready` | database readiness (`SELECT 1`, three-second timeout): 200 `ready` or sanitized 503 `unavailable`; uncached; includes a validated full `RENDER_GIT_COMMIT` as `revision` when available |
| GET | `/auth/config` | `{github_login_enabled}`: whether GitHub sign-in is set up on this server |
| GET | `/auth/github/login` | start sign-in: redirects to GitHub (sets a short-lived `oauth_state` cookie) |
| GET | `/auth/github/callback` | GitHub returns here; creates/updates the user, saves the token encrypted, sets the session cookie, redirects to the frontend |
| GET | `/auth/me` | the signed-in user (401 if not signed in); `github_connected` says a token is saved |
| POST | `/auth/logout` | clears the session cookie |
| POST | `/auth/github/disconnect` | deletes the saved encrypted GitHub credential and leaves the CODEVERSE session active; revoke the OAuth grant separately in GitHub settings if needed |
| GET | `/github/repos?page=&per_page=&q=` | repos the signed-in user can access on GitHub (public and private); `q` filters the page |
| GET | `/github/branches?repo=owner/name` | default branch and branch names (first 100) |
| POST | `/repos` | `{url, branch?, access_token?}` register + enqueue indexing (202). Idempotent per user+url+branch |
| POST | `/repos/{id}/reindex` | re-run indexing (atomic swap, old data stays readable until done) |
| GET | `/repos`, `/repos/{id}` | status (`queued/indexing/ready/failed`), `stage`, `error`, summary, tech stack, report, warnings |
| GET | `/repos/{id}/map` | modules (each with `depends_on`, `used_by`, `relationship_summary`), entry points, module-to-module dependency graph (for React Flow) |
| DELETE | `/repos/{id}` | delete the owned repository and all derived index data (blocked while indexing) |
| GET | `/repos/{id}/history?path=&limit=50` | latest GitHub commits and contribution counts from that sample; optional file/folder path filter; fetched on demand and not stored. Empty repo -> empty history; expired GitHub sign-in -> 403 `github_reauth_required` |
| GET | `/repos/{id}/files`, `/files/{path}` | file tree; per file: symbols, imports, imported_by |
| GET | `/repos/{id}/source/{path}` | on-demand source at the indexed commit with secrets redacted; indexed files only (403 for sensitive ones), capped at 500 KB |
| GET | `/repos/{id}/explain?file=\|symbol=&refresh=` | beginner-friendly explanation of one file or function + how it relates to the rest (see below) |
| GET | `/repos/{id}/symbols?q=` | find functions/classes |
| POST | `/repos/{id}/search` | hybrid retrieval, no LLM: `{query, k}` |
| POST | `/repos/{id}/ask` | `{question, symbol?, file?, depth?}`: "what would break if I change X?" is answered from the import/call graphs; any other question is RAG with validated citations (see below) |
| POST | `/repos/{id}/ask/stream` | `{question, conversation_id?, symbol?, file?, depth?}`: streams a grounded answer (Server-Sent Events: `conversation`, `sources`, `token`, `result`, `error`, `done`) and saves both messages. Earlier completed turns of the conversation (last 12) come from the database; a failed or interrupted answer is saved as `failed` and is not sent to the model again. Without `conversation_id` a new conversation is created |
| GET | `/repos/{id}/conversations` | your saved conversations, most recently active first; `limit=50` (max 100), `offset=0` |
| POST | `/repos/{id}/conversations` | `{title?}`: start a conversation; while your newest one is still empty it is returned again instead of creating another |
| GET | `/repos/{id}/conversations/{conversation_id}/messages` | latest `limit=100` messages (max 200), returned chronologically; `offset` pages backwards; bounded legacy excerpts have `truncated=true` |
| DELETE | `/repos/{id}/conversations/{conversation_id}` | explicitly delete an owned chat and its messages; `409` while an answer is pending |
| GET | `/repos/{id}/impact?symbol=\|file=&depth=&explain=` | "what breaks if I change this" (reverse traversal); same report the Ask box shows, with a call chain and a reason per item |

Streaming Q&A clients send the new `question`, `conversation_id` and optional `symbol`/`file`/`depth`
hints, not earlier messages. The database is the only source of prior conversation context, after
repository and conversation ownership checks. The bounded recent-history selection and 4,000-character
per-context-message limit remain in place; these do not shorten the saved answer or its browser display.

For older browser tabs, `AskStreamIn.history` remains a deprecated compatibility field. Any supplied
value is discarded before turn validation, never persisted or sent to the AI, and excluded from model
serialization. Old clients replaying answers longer than 4,000 characters therefore do not invalidate
an otherwise valid follow-up. This is not an HTTP request-body size limit: JSON still has to be parsed.
After client rollout and testing-team confirmation, remove the deprecated field and its discard validator;
new clients must not depend on it. Backend regressions are in `tests/test_qa_history.py`.

Every `/repos` and `/github` route needs the session cookie (401 otherwise), and a user only ever sees their own
repositories: someone else's repo answers 404, the same as a missing one. Poll `GET /repos/{id}` for progress; the
other repo endpoints return 409 until `status == "ready"`.

Errors worth handling in a client: `403` with `detail.code == "github_reauth_required"` (the saved GitHub token was
revoked or can no longer be read: sign in with GitHub again), `429` (GitHub rate limit), `404` (not found or not
accessible with this GitHub account).

### Tasks and saved progress

The Tasks page supports ongoing per-user, per-repository task management. Tasks are persisted in PostgreSQL and support pending, in-progress, and completed statuses; sources include AI-generated, manually added, and synchronized GitHub issues.

| Managed tasks endpoint | Purpose |
|---|---|
| `GET /repos/{id}/tasks` | List persisted tasks and synchronization status |
| `POST /repos/{id}/tasks` | Create a manual task |
| `POST /repos/{id}/tasks/generate` | Generate additional repository-aware AI tasks |
| `PATCH /repos/{id}/tasks/{task_key}` | Update a task or its status |
| `DELETE /repos/{id}/tasks/{task_key}` | Delete a task while retaining its generation history |

The following original onboarding endpoints are retained for backward compatibility:


| Endpoint | Purpose |
|---|---|
| `POST /repos/{id}/issues/sync` | Fetch beginner-friendly open issues from GitHub (background job); poll `GET` on the same path |
| `GET /repos/{id}/onboarding-tasks` | The plan: issues (easiest first) plus orientation tasks when fewer than 3 issues suit a newcomer |
| `PUT /repos/{id}/onboarding-tasks/{key}/progress` | Save status for a real task in this user's ready repository; invented/ineligible keys return `404`; `pending` removes its progress row |

Every task in the plan carries a stable `key` (`issue-<number>` or `gen-<slug>`) and the user's saved `status`
(`pending` when nothing is saved). Progress lives in the `task_progress` table, one row per user, repository and
task, so it survives other devices and browsers and is never visible to another user. Rows are deleted with the
repository or the user.

### Private repositories

Sign in with GitHub and register the repo URL: nothing else is needed. The indexing job first tries an anonymous clone
(so public repos never use your token, and a revoked token cannot break them); if that fails it clones with the token
saved at sign-in. The token is decrypted only inside the indexing job for that clone and is never put in the job queue,
logs or API responses. Pasting a token as `access_token` on `POST /repos` or `/reindex` still works and takes
priority; that one is passed through the queue for the job and never stored.

Issue sync (both automatic after indexing and manually requested) uses an explicitly supplied
`access_token` first, then the repository owner's saved OAuth credential, then the server's
`GITHUB_TOKEN` only when no user credential exists; otherwise it can fetch public issues anonymously.
Saved credentials are loaded/decrypted inside the sync job, not copied into its queue arguments.
Unreadable or rejected saved credentials do not silently fall back to the server's identity:
the sync reports a sign-in/access-permissions hint and keeps previously cached issues. Rate limits
and network failures also preserve the cache. Re-sign in to refresh a revoked token, or check
repository access and organization OAuth app approval for permission failures.

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
| `MAX_CONCURRENT_INDEXING` | `1` | repositories indexed at the same time (indexing is memory-heavy) |
| `JOB_TIMEOUT_SECONDS` | `1800` | a background job running longer than this is marked failed |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `5` / `2` | connection pool size; keep small on free Postgres hosts |
| `DB_POOL_RECYCLE_SECONDS` | `300` | replaces pooled connections before the host closes them when idle |
| `DB_CONNECT_TIMEOUT_SECONDS` | `30` | a sleeping Neon database needs a few seconds to wake up |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON list; only matters when the browser calls the API directly. Compose also sets it, which takes precedence over `.env` |
| `EMBED_BACKEND`, `EMBED_MODEL`, `EMBED_DIM` | `cloudflare`, `@cf/baai/bge-small-en-v1.5`, `384` | embeddings: `cloudflare` (hosted Workers AI, see below) or `hash` (tests only) |
| `CF_ACCOUNT_ID`, `CF_API_TOKEN` | empty | Cloudflare Workers AI credentials, required for indexing and search (`CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` also work) |
| `EMBED_BATCH_SIZE` | `128` | chunks embedded per progress step |
| `EMBED_CF_BATCH_SIZE`, `EMBED_CF_CONCURRENCY` | `50`, `4` | texts per Cloudflare request (max 100) and requests in flight |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | empty | GitHub OAuth app credentials (for login and private repos) |
| `GITHUB_REDIRECT_URI` | `http://localhost:5173/api/auth/github/callback` | must match the OAuth app's callback URL exactly |
| `FRONTEND_URL` | `http://localhost:5173` | where the browser is sent after login |
| `SESSION_SECRET` | empty | signs the login cookie; at least 32 characters |
| `SESSION_COOKIE_NAME`, `SESSION_TTL_SECONDS`, `COOKIE_SECURE` | `session`, 7 days, `false` | cookie settings; set `COOKIE_SECURE=true` behind https |
| `TOKEN_ENCRYPTION_KEY` | empty | Fernet key that encrypts stored GitHub tokens; comma-separate several keys to rotate |
| `MAX_CHUNKS`, `MAX_FILE_BYTES` | `5000`, `200000` | indexing caps |
| `MAX_CLONE_BYTES` | `209715200` | 200 MiB aggregate clone/worktree disk watchdog budget; also Linux per-file hard cap |
| `MAX_CHECKOUT_BYTES`, `MAX_CLONE_FILE_BYTES` | `104857600`, `20971520` | reject expanded trees over 100 MiB or individual files over 20 MiB before checkout |
| `CLONE_MEMORY_BYTES`, `CLONE_CPU_SECONDS` | `268435456`, `120` | Linux hard per-process address-space (256 MiB) and CPU limits for Git and descendants |
| `CLONE_TIMEOUT_SECONDS` | `300` | shared wall-clock deadline for clone, size inspection and checkout |
| `CLONE_MIN_FREE_DISK_BYTES` | `268435456` | reserve at least 256 MiB free on the temporary work filesystem |
| `RATE_LIMIT_ENABLED` | `true` | master switch for the per-user request limits below |
| `RATE_LIMIT_LLM_PER_MINUTE`, `RATE_LIMIT_LLM_PER_HOUR` | `10`, `100` | shared per-user AI budget: Q&A, explanation generation, and `explain=true` on impact/tasks |
| `RATE_LIMIT_READ_PER_MINUTE` | `60` | `/search`, `/explain`, `/impact`, `/onboarding-tasks` per user |
| `RATE_LIMIT_INDEX_PER_HOUR` | `10` | add, re-index and issue-sync requests per user |
| `RATE_LIMIT_REFRESH_PER_HOUR` | `5` | extra `/explain?refresh=true` request budget; actual generation also consumes AI quota |
| `RATE_LIMIT_WRITE_PER_MINUTE` | `60` | shared per-user budget for progress writes and chat create/delete |
| `MAX_REPOS_PER_USER` | `5` | repositories one account can keep (`403` beyond that) |
| `MAX_ACTIVE_JOBS_PER_USER` | `2` | repositories one account can have queued or indexing at once (`429`) |
| `MAX_TOTAL_CHUNKS` | `60000` | code chunks stored for all users together (about 270 MB; keeps Neon's free tier from filling up) |
| `MAX_TASK_PROGRESS_PER_REPO`, `MAX_TOTAL_TASK_PROGRESS` | `200`, `20000` | stored non-pending progress rows per owned repository / server |
| `MAX_CONVERSATIONS_PER_REPO`, `MAX_CONVERSATIONS_PER_USER`, `MAX_TOTAL_CONVERSATIONS` | `20`, `100`, `5000` | conversation row caps; empty-chat reuse is still permitted |
| `MAX_MESSAGES_PER_CONVERSATION`, `MAX_MESSAGES_PER_USER`, `MAX_TOTAL_MESSAGES` | `100`, `2000`, `20000` | message row caps, counting pending/failed messages; each turn needs two slots |
| `MAX_MESSAGE_CONTENT_BYTES`, `MAX_MESSAGE_CITATIONS_BYTES` | `32000`, `8192` | persisted UTF-8 message/JSON citation payload bounds |
| `CONVERSATION_STREAM_TIMEOUT_SECONDS` | `120` | wall-clock limit on the model's answer stream |
| `STORAGE_BUDGET_BYTES`, `STORAGE_CHUNK_BYTES` | `419430400`, `6000` | shared 400 MiB planning budget; minimum estimated bytes per chunk |
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

Every `/explain` request consumes the read budget. A file or symbol explanation that needs a new
LLM generation also consumes the signed-in user's shared AI budget, immediately before generation.
This includes stale-cache misses and forced refreshes. A cache hit or relationship-only response
(sensitive file, no indexed text, or missing LLM configuration) does not consume AI quota.
When AI quota is exhausted, generation returns `429` with `Retry-After` without calling the model
or changing the cache; existing cached explanations remain available within the read limit.
Failed provider attempts still consume AI quota. Refresh requests retain their additional small
refresh budget; the normal AI budget is not bypassed by requesting a refresh.

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
symbol-aware chunks -> Cloudflare embeddings -> one atomic DB swap -> LLM module map + summary (validated, with fallback).

README input for both LLM descriptions is limited to regular root-level text files (no symlinks or
sensitive filenames). Files over 200 KB or containing NUL bytes are skipped. Secrets are redacted
before the text is shortened for the prompt, including secrets crossing the prompt boundary.

Content redaction covers known token formats, quoted/unquoted secret assignments, credential-bearing
URIs (including database connection strings), and Bearer/Basic authorization values. It preserves
line breaks for citations. Redaction is best-effort, not a guarantee: scan private code with a
dedicated tool such as gitleaks before uploading it. Re-index existing repositories after a redaction
update; this does not remove historical AI-provider requests, logs, or database backups. Rotate any
credentials that may already have been disclosed.

### Clone resource protection

GitHub's reported repository size is screened before downloading (private repositories use the
job's credential). This estimate includes history and can conservatively reject a large repository
whose current branch is small. Missing metadata or GitHub rate limits do not disable the other checks.

Git clones shallowly **without checkout** and without local hardlinks. The expanded tree's file
count, total bytes and individual blob sizes are checked before checkout. LFS smudging and recursive
submodules are not enabled. All Git phases share a wall-clock deadline, bounded output capture,
an aggregate disk watchdog, and a free-disk reserve. Failed operations kill/reap the process tree
before deleting the partial clone. Resource-limit failures are not retried with a saved OAuth token.

Production Docker/Linux additionally applies hard kernel limits for address space, CPU time and
per-file disk size to Git subprocesses, with one pack thread. These are **per process**, not a
whole-job memory/CPU quota; the hosting container remains the outer memory boundary. Windows
development uses the disk/time watchdog but does not provide the Linux kernel limits.

The aggregate disk watchdog samples between operations and can overshoot its threshold between
checks. A strict aggregate disk boundary requires a quota-limited work filesystem/container volume
configured on the host; do not treat the watchdog as a filesystem quota. Keep indexing concurrency
at one on Render's 512 MB tier and lower clone limits if needed.

## What changed vs. the first AI-team version

| Problem | Fix |
|---|---|
| `index_repo` wiped the shared `vector_store` folder on every run | pgvector rows keyed by `repo_id`; reindex replaces one repo atomically |
| `.env` never loaded; embedding model reloaded on every call | settings via pydantic-settings; embedder and LLM are process singletons |
| Chroma on local disk, unsafe across API + worker processes | Postgres + pgvector (exact cosine search, filtered by repo) + Postgres full-text, fused with RRF |
| torch + MiniLM (256-token window, general text) | Cloudflare Workers AI `bge-small` (512 tokens); another model is a config switch plus a migration |
| Random sampling at the chunk cap | files ranked (README, entry points, import-graph hubs first, tests last) |
| Character-based chunks | tree-sitter chunks per function/method/class header, exact line ranges |
| LLM guessed structure from names | import-graph facts (hubs, entry candidates, folder dependencies) go into the prompt; paths validated |
| Everything synchronous | async LLM calls; blocking work in threads; in-process background jobs |
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
| `Embeddings` interface | `ai_pipeline/embeddings.py` | Cloudflare Workers AI; swap in any LangChain embeddings class |
| `Document` | `chunker.py` | one Document per function/class, metadata carries file path and exact lines |
| `BaseRetriever` | `app/services/retrieval.py` `PgHybridRetriever` | wraps OUR pgvector + full-text SQL; the vector store itself is not LangChain's |

Deliberately NOT LangChain: the pgvector tables and hybrid SQL, tree-sitter chunking (LangChain's splitters cannot give
function-level chunks with exact line numbers), and the NetworkX graphs.

## Known limits (honest list)

- Impact analysis follows calls and imports only: subclasses, `except SomeError` handlers and `isinstance` checks are not edges, so changing a class or exception can affect more than the list shows.
- Call/impact analysis is static and name-based: dynamic dispatch, reflection and string imports are invisible, and a
  call to an unknown receiver (`x.save()`) only resolves inside the same file or imported files. The API says so in `caveat`.
- Only Python, JS/JSX and TS/TSX are parsed; other languages are indexed as line-window text chunks (still searchable).
- Whole files are not stored after indexing (the clone is deleted, DR-03); source is fetched on demand from GitHub at the pinned index commit, and only indexed non-sensitive files up to 500 KB are shown.
- Secret redaction is regex-based. For production add gitleaks in the indexing job.
- `tree-sitter` is pinned `<0.26`: 0.26.0 segfaulted in the Python binding on larger files.
- Changing `EMBED_DIM` needs a new Alembic migration and a reindex of every repo.
- `google_genai:gemini-3.6-flash` is the default `LLM_MODEL`: confirm in AI Studio that it is available on your free tier.
- Old `.env` files: `GOOGLE_API_KEY` still works, but `GEMINI_MODEL` is ignored now. Use `LLM_MODEL=google_genai:<model>`.
- Not built yet: webhook re-indexing.
- Private-repo access uses GitHub's broad `repo` OAuth scope (read and write at GitHub's end; this app only reads). A
  GitHub App with per-repo installs would be the least-privilege upgrade.
- Organizations that restrict third-party apps must approve this OAuth app before their private repos can be cloned.

## Later, when you move to paid services

- Gemini paid tier: only billing and `LLM_MIN_INTERVAL_SECONDS` change.
- Hosted embeddings (Voyage, Google, OpenAI): return any LangChain `Embeddings` class from `get_embedder()` in
  `ai_pipeline/embeddings.py`, set `EMBED_DIM`, add a migration if the size differs, reindex.
- Large repos: add an HNSW index (pgvector >= 0.8 with iterative scans), or move vectors to Qdrant.


## Cloudflare Workers AI embeddings

Embeddings come from Cloudflare's hosted `@cf/baai/bge-small-en-v1.5` (384 dimensions). Nothing is downloaded and the
server needs very little RAM.

1. Cloudflare dashboard -> AI -> Workers AI -> "Use REST API": copy the **Account ID** and create an API token with the Workers AI permission.
2. In `backend/.env`: `CF_ACCOUNT_ID=...` and `CF_API_TOKEN=...` (the other embedding settings already default to Cloudflare).
3. `uv run python check_embeddings.py` verifies the credentials, the vector size and the speed.
4. If you migrated from an older local-model install, **re-index every repo**: the old vectors came from a different model setup.

The free allowance is 10,000 neurons per day (reset 00:00 UTC), shared by all Workers AI models. bge-small costs 1,841 neurons
per million input tokens, so roughly 5 million tokens a day; a typical repo uses a few hundred neurons and one at the
5,000-chunk cap about 2,200 to 2,700. When the allowance runs out, indexing fails with a clear message and works again after
the reset. See Workers AI in the Cloudflare dashboard for today's usage, and check Cloudflare's pricing page for the current
numbers. Chunk text is sent to Cloudflare, so think about that before indexing private repos.


## Abuse protection (rate limits and quotas)

Anyone with a GitHub account can sign in, so the free tiers behind the app (Gemini, Cloudflare Workers AI, Neon) are
protected in two ways. Defaults are in `app/core/config.py`; every number can be changed with the variables above.

- **Rate limits** (`app/core/ratelimit.py`): per user, sliding window, answered with `429` and a `Retry-After` header.
  Five budgets: *llm* (`/ask`, `/ask/stream`, uncached/refreshed file or symbol explanation generation,
  and `explain=true` on `/impact` and `/onboarding-tasks`), *read*
  (`/search`, `/explain`, `/impact`, `/onboarding-tasks`), *index* (add, re-index, issue sync) and *refresh*
  (`/explain?refresh=true`), and *write* (task progress and chat create/delete). The counters live in the API process.
  The app runs as one process, so they are exact;
  if you ever run several processes, each counts separately and the counters should move to Redis.
- **Quotas** (`app/services/limits.py`): at most `MAX_REPOS_PER_USER` repositories and `MAX_ACTIVE_JOBS_PER_USER`
  queued/indexing repositories per account, and `MAX_TOTAL_CHUNKS` stored chunks across all users. A repository that
  would not fit fails during indexing, before any embedding call, so it spends no Cloudflare quota. Deleting a
  repository frees its share.

### Progress and conversation storage

Progress keys must identify either a synced eligible issue in that repository or an orientation task
derived from its current indexed data. Validation does not call embeddings, GitHub or the LLM.
Orientation tasks remain valid if a different plan limit hides them. Invented keys cannot allocate
rows. Setting status to `pending` deletes the row (absence already means pending); updates to existing
valid rows still work when row capacity is full.

Chat and progress row caps and their storage reservations are checked in a short transaction protected
by a shared PostgreSQL advisory lock. This also covers the final indexing swap, so concurrent writers
cannot separately reserve the same remaining capacity. Repository registration/queue quotas retain
their existing best-effort checks. No storage lock is held while waiting for an embedding or LLM call.

Before streaming starts, the server reserves BOTH a question row and a pending-answer row, plus a
conversation slot when needed. Every message reserves its full configured content/citation allowance,
including failed/pending rows. Answers are stopped at their UTF-8 byte cap or stream timeout and marked
failed, never silently marked complete after truncation. Citation paths are not cut into invented paths.
Only 24 recent message rows are read to assemble the last 12 completed context messages.

The shared planning estimate includes:
- chunks: at least `STORAGE_CHUNK_BYTES`, or UTF-8 content + vector bytes + 1 KiB allowance, whichever is larger;
- task progress: 1 KiB per row;
- conversations: 2 KiB per row;
- messages: content/citation caps + 1 KiB per row, or the larger actual payload for legacy records.

The shared budget may be reached before any individual row cap. It is checked before embedding and
rechecked at the atomic save. Reindexing replaces, rather than double-counts, its previous chunks.
Non-growing updates and deletions remain allowed when a configured budget is lowered.

Per-account/owned-repository caps return `403`; global row/planning-budget exhaustion returns `503`;
write-rate exhaustion returns `429` with `Retry-After`. An oversized question returns `413` before
allocating rows. Users can explicitly delete chats (with message cascade), delete an indexed repository,
or reset progress to free application capacity. The UI distinguishes **New chat** (keeps earlier chats)
from confirmed **Delete chat**. On single-process API startup, interrupted pending answers become failed,
so they do not permanently prevent chat deletion.

**Existing data is not automatically deleted or rewritten.** Larger legacy payloads are counted in
planning and returned as bounded, marked excerpts. Old invented progress rows are included in caps;
an administrator may review them manually, or the owner can remove the repository and its derived data.

This estimate is **not a physical PostgreSQL/Neon disk quota**. Other derived tables, indexes, WAL,
backups and database bloat still need headroom and monitoring in Neon. Deleting rows releases logical
capacity immediately, but does not guarantee an immediate reduction in physical database size.
