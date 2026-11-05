# Codebase Onboarding Companion: backend + AI pipeline

FastAPI + Alembic + Postgres/pgvector + ARQ (Redis) + tree-sitter + NetworkX. Everything here runs on free
tools: local ONNX embeddings (fastembed), the Gemini free tier for the LLM steps (through LangChain), no paid service required.

## Run it

From the repository root:

```bash
cp backend/.env.example backend/.env   # put your free LLM_API_KEY in it (optional, see below; the old name GOOGLE_API_KEY still works)
docker compose up --build              # db, redis, migrations, api (:8000), worker
open http://localhost:8000/docs
```

Without Docker (uv only, no pip/venv/requirements.txt): start Postgres with the pgvector extension and Redis, then
```bash
cd backend
uv sync                                   # creates .venv from uv.lock
uv run alembic upgrade head
uv run uvicorn app.main:app --reload      # terminal 1
uv run arq app.worker.WorkerSettings      # terminal 2
```
Add a dependency with `uv add <pkg>`; commit `pyproject.toml` and `uv.lock` together. First indexing downloads the embedding model (~130 MB) once.

No `LLM_API_KEY`? Everything still works except `/ask` and `/impact?explain=true` (503). The module map falls back
to a deterministic one built from the import graph, and the repo summary is skipped (with a warning in the response).

Tests (real Postgres + pgvector needed, they skip otherwise): `cd backend && uv run pytest`
(point `DATABASE_URL` at a scratch database; the suite runs the Alembic migration up and down).

## API

| Method | Path | What |
|---|---|---|
| POST | `/repos` | `{url, branch?, access_token?}` register + enqueue indexing (202). Idempotent per url+branch |
| POST | `/repos/{id}/reindex` | re-run indexing (atomic swap, old data stays readable until done) |
| GET | `/repos`, `/repos/{id}` | status (`queued/indexing/ready/failed`), `stage`, `error`, summary, tech stack, report, warnings |
| GET | `/repos/{id}/map` | modules, entry points, module-to-module dependency graph (for React Flow) |
| GET | `/repos/{id}/files`, `/files/{path}` | file tree; per file: symbols, imports, imported_by |
| GET | `/repos/{id}/symbols?q=` | find functions/classes |
| POST | `/repos/{id}/search` | hybrid retrieval, no LLM: `{query, k}` |
| POST | `/repos/{id}/ask` | RAG answer with validated citations: `{question}` |
| GET | `/repos/{id}/impact?symbol=\|file=&depth=&explain=` | "what breaks if I change this" (reverse traversal) |

Poll `GET /repos/{id}` for progress; the other endpoints return 409 until `status == "ready"`.

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

- Call/impact analysis is static and name-based: dynamic dispatch, reflection and string imports are invisible, and a
  call to an unknown receiver (`x.save()`) only resolves inside the same file or imported files. The API says so in `caveat`.
- Only Python, JS/JSX and TS/TSX are parsed; other languages are indexed as line-window text chunks (still searchable).
- File contents are not stored after indexing (the clone is deleted, DR-03). The UI should fetch source from GitHub.
- Secret redaction is regex-based. For production add gitleaks in the worker.
- `tree-sitter` is pinned `<0.26`: 0.26.0 segfaulted in the Python binding on larger files.
- Changing `EMBED_DIM` needs a new Alembic migration and a reindex of every repo.
- `google_genai:gemini-3.6-flash` is the default `LLM_MODEL`: confirm in AI Studio that it is available on your free tier.
- Old `.env` files: `GOOGLE_API_KEY` still works, but `GEMINI_MODEL` is ignored now. Use `LLM_MODEL=google_genai:<model>`.
- Not built yet: first-week task list from GitHub issues, SSE streaming for `/ask`, auth/users, webhook re-indexing.

## Later, when you move to paid services

- Gemini paid tier: only billing and `LLM_MIN_INTERVAL_SECONDS` change.
- Hosted embeddings (Voyage, Google, OpenAI): return any LangChain `Embeddings` class from `get_embedder()` in
  `ai_pipeline/embeddings.py`, set `EMBED_DIM`, add a migration if the size differs, reindex.
- Large repos: add an HNSW index (pgvector >= 0.8 with iterative scans), or move vectors to Qdrant.
