# Codebase Onboarding Companion

Maps an unfamiliar repository, explains key files in plain English, answers questions about the code,
and shows what breaks when a function changes.

```
.
├── backend/                 Python project: FastAPI API + AI pipeline (see backend/README.md)
│   ├── app/                 FastAPI app: api/, core/, db/, services/, models.py, schemas.py, worker.py
│   ├── ai_pipeline/         parser, graph, chunker, embeddings, LLM chains (imported by app/)
│   ├── alembic/             database migrations
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml, uv.lock
│   └── .env.example
├── docker-compose.yml       db (pgvector), redis, migrate, api, worker
└── .gitignore
```

## Quick start

```bash
cp backend/.env.example backend/.env
docker compose up --build
# API docs: http://localhost:8000/docs
```

Full backend documentation: [backend/README.md](backend/README.md).
